"""Generate the synthetic evaluation set: invoices and receipts with known ground truth.

Every document is fictional and generated from a fixed seed, so the set is reproducible and free to
publish. Documents vary the things that break extraction in practice: number formats (1,234.56 /
1.234,56 / 1 234,56), date formats (03/14/2026, 14/03/2026, 14.03.2026, 14 mars 2026), languages,
missing optional fields, and scans (rendered, rotated, noisy images) that have to go through OCR.

The generator checks its own output: every ground-truth quote must be found verbatim in the rendered
PDF's text layer, or generation fails. That is the positive control for the anchoring evals.

    python evals/generate.py            # writes evals/dataset/
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ex_app" / "lib"))

from pinpoint.anchor import DocumentIndex
from pinpoint.document import LoadOptions, load_document

DATASET = Path(__file__).resolve().parent / "dataset"


@dataclass(frozen=True)
class Locale:
    code: str
    words: dict[str, str]
    decimal: str
    thousands: str
    currency: str
    symbol_after: bool

    def money(self, amount: float) -> str:
        whole, frac = f"{amount:,.2f}".split(".")
        whole = whole.replace(",", self.thousands)
        number = f"{whole}{self.decimal}{frac}"
        symbol = {"EUR": "€", "USD": "$", "GBP": "£"}[self.currency]
        return f"{number} {symbol}" if self.symbol_after else f"{symbol}{number}"

    def date(self, d: date) -> str:
        if self.code == "en-US":
            return d.strftime("%m/%d/%Y")
        if self.code == "en-GB":
            return d.strftime("%d/%m/%Y")
        if self.code == "de-DE":
            return d.strftime("%d.%m.%Y")
        months = [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ]
        return f"{d.day} {months[d.month - 1]} {d.year}"


LOCALES = [
    Locale(
        "en-US",
        {
            "invoice": "Invoice",
            "number": "Invoice No.",
            "date": "Invoice date",
            "due": "Due date",
            "net": "Subtotal",
            "tax": "Sales tax",
            "total": "Total due",
            "qty": "Qty",
            "item": "Description",
            "price": "Amount",
            "bill_to": "Bill to",
            "pay": "Please pay to",
            "receipt": "Receipt",
            "paid_card": "Paid by card",
            "paid_cash": "Paid in cash",
            "tax_incl": "Tax included",
        },
        ".",
        ",",
        "USD",
        False,
    ),
    Locale(
        "en-GB",
        {
            "invoice": "Invoice",
            "number": "Invoice number",
            "date": "Date",
            "due": "Payment due",
            "net": "Net",
            "tax": "VAT 20%",
            "total": "Total",
            "qty": "Qty",
            "item": "Item",
            "price": "Price",
            "bill_to": "Invoice to",
            "pay": "Bank details",
            "receipt": "Receipt",
            "paid_card": "Card payment",
            "paid_cash": "Cash",
            "tax_incl": "VAT included",
        },
        ".",
        ",",
        "GBP",
        False,
    ),
    Locale(
        "de-DE",
        {
            "invoice": "Rechnung",
            "number": "Rechnungsnummer",
            "date": "Rechnungsdatum",
            "due": "Zahlbar bis",
            "net": "Nettobetrag",
            "tax": "MwSt. 19 %",
            "total": "Gesamtbetrag",
            "qty": "Menge",
            "item": "Beschreibung",
            "price": "Betrag",
            "bill_to": "Rechnung an",
            "pay": "Bankverbindung",
            "receipt": "Kassenbon",
            "paid_card": "Kartenzahlung",
            "paid_cash": "Bar bezahlt",
            "tax_incl": "enthaltene MwSt.",
        },
        ",",
        ".",
        "EUR",
        True,
    ),
    Locale(
        "fr-FR",
        {
            "invoice": "Facture",
            "number": "Facture n°",
            "date": "Date",
            "due": "Échéance",
            "net": "Total HT",
            "tax": "TVA 20 %",
            "total": "Total TTC",
            "qty": "Qté",
            "item": "Désignation",
            "price": "Montant",
            "bill_to": "Client",
            "pay": "Coordonnées bancaires",
            "receipt": "Ticket",
            "paid_card": "Payé par carte",
            "paid_cash": "Payé en espèces",
            "tax_incl": "dont TVA",
        },
        ",",
        "\u202f",
        "EUR",
        True,
    ),
]

SUPPLIERS = [
    "Nordlicht Bürobedarf GmbH",
    "Harbour & Finch Design Ltd",
    "Atelier Verte SARL",
    "Bluefield Analytics LLC",
    "Kestrel Print Studio",
    "Lindqvist Consulting AB",
    "Maison Ocre Traiteur",
    "Pinecrest Software Inc.",
]
CUSTOMERS = ["Weber Logistik AG", "Ruth Okafor", "Studio Halvorsen", "Greenway Clinic", "Café Amsel"]
ITEMS = [
    ("Consulting, March", 640.0),
    ("Website maintenance", 180.0),
    ("Printing, 500 flyers", 92.5),
    ("Office chairs", 249.0),
    ("Catering for 12", 312.0),
    ("Annual licence", 1188.0),
    ("Toner cartridge", 64.9),
    ("Workshop day", 950.0),
    ("Translation, 3 pages", 135.0),
    ("Paper A4, 10 reams", 47.8),
]
MERCHANTS = ["Bäckerei Sonnenschein", "Corner Market", "Librairie du Port", "Green Leaf Café", "Tankstelle Ost"]
IBANS = ["DE89 3704 0044 0532 0130 00", "GB33 BUKB 2020 1555 5555 55", "FR14 2004 1010 0505 0001 3M02 606"]


def _invoice(rng: random.Random, n: int, locale: Locale) -> tuple[str, dict]:
    supplier = SUPPLIERS[n % len(SUPPLIERS)]
    customer = rng.choice(CUSTOMERS)
    number = f"{rng.choice(['INV', 'RE', 'F', '2026'])}-{rng.randint(1000, 9999)}"
    # Days above 12 keep slash dates unambiguous on most documents; a few ambiguous ones stay on purpose.
    issued = date(2026, rng.randint(1, 10), rng.randint(1, 28) if n % 5 == 0 else rng.randint(13, 28))
    due = issued + timedelta(days=rng.choice([14, 30])) if n % 4 != 3 else None
    rate = 0.19 if locale.code == "de-DE" else 0.2 if locale.code in ("en-GB", "fr-FR") else 0.08
    lines = rng.sample(ITEMS, rng.randint(1, 4))
    quantities = [rng.randint(1, 3) for _ in lines]
    subtotal = round(sum(q * p for q, (_, p) in zip(quantities, lines, strict=True)), 2)
    tax = round(subtotal * rate, 2)
    total = round(subtotal + tax, 2)
    iban = rng.choice(IBANS) if n % 3 != 2 else None
    w = locale.words
    rows = "".join(
        f"<tr><td>{item}</td><td style='text-align:right'>{q}</td>"
        f"<td style='text-align:right'>{locale.money(q * price)}</td></tr>"
        for q, (item, price) in zip(quantities, lines, strict=True)
    )
    html = f"""
    <div style="font-family: sans-serif; font-size: 10pt;">
      <p style="font-size: 16pt; font-weight: bold;">{supplier}</p>
      <p>{rng.randint(1, 99)} {rng.choice(["Harbour Road", "Lindenstraße", "Rue des Lilas", "Market Street"])}</p>
      <p style="font-size: 14pt; font-weight: bold;">{w["invoice"]}</p>
      <p>{w["number"]}: {number}</p>
      <p>{w["date"]}: {locale.date(issued)}</p>
      {f"<p>{w['due']}: {locale.date(due)}</p>" if due else ""}
      <p>{w["bill_to"]}: {customer}</p>
      <table style="width: 100%;">
        <tr><th style="text-align:left">{w["item"]}</th><th style="text-align:right">{w["qty"]}</th>
            <th style="text-align:right">{w["price"]}</th></tr>
        {rows}
      </table>
      <p>{w["net"]}: {locale.money(subtotal)}</p>
      <p>{w["tax"]}: {locale.money(tax)}</p>
      <p style="font-weight: bold;">{w["total"]}: {locale.money(total)}</p>
      {f"<p>{w['pay']}: IBAN {iban}</p>" if iban else ""}
    </div>"""
    truth = {
        "template": "invoice",
        "locale": locale.code,
        "fields": {
            "supplier": {"value": supplier, "quote": supplier},
            "invoice_number": {"value": number, "quote": number},
            "issue_date": {"value": issued.isoformat(), "quote": locale.date(issued)},
            "due_date": {"value": due.isoformat() if due else None, "quote": locale.date(due) if due else None},
            "currency": {"value": locale.currency, "quote": locale.money(total)},
            "subtotal": {"value": subtotal, "quote": locale.money(subtotal)},
            "tax": {"value": tax, "quote": locale.money(tax)},
            "total": {"value": total, "quote": locale.money(total)},
            "iban": {"value": iban, "quote": iban},
        },
    }
    return html, truth


def _receipt(rng: random.Random, n: int, locale: Locale) -> tuple[str, dict]:
    merchant = MERCHANTS[n % len(MERCHANTS)]
    bought = date(2026, rng.randint(1, 10), rng.randint(13, 28))
    items = [
        (name, round(rng.uniform(1.2, 14.0), 2))
        for name in rng.sample(
            ["Coffee", "Croissant", "Notebook", "Sandwich", "Water 1l", "Pens (3)", "Newspaper", "Apples 1kg"], 3
        )
    ]
    total = round(sum(p for _, p in items), 2)
    rate = 0.07 if locale.code == "de-DE" else 0.1
    tax = round(total - total / (1 + rate), 2) if n % 3 != 1 else None
    card = n % 2 == 0
    w = locale.words
    rows = "".join(f"<p>{name} ...... {locale.money(price)}</p>" for name, price in items)
    html = f"""
    <div style="font-family: monospace; font-size: 9pt;">
      <p style="font-weight: bold;">{merchant}</p>
      <p>{w["receipt"]} {rng.randint(10000, 99999)}</p>
      <p>{locale.date(bought)} {rng.randint(8, 19)}:{rng.randint(10, 59)}</p>
      {rows}
      <p style="font-weight: bold;">{w["total"].upper()} {locale.money(total)}</p>
      {f"<p>{w['tax_incl']} {locale.money(tax)}</p>" if tax is not None else ""}
      <p>{w["paid_card"] if card else w["paid_cash"]}</p>
    </div>"""
    truth = {
        "template": "receipt",
        "locale": locale.code,
        "fields": {
            "merchant": {"value": merchant, "quote": merchant},
            "date": {"value": bought.isoformat(), "quote": locale.date(bought)},
            "currency": {"value": locale.currency, "quote": locale.money(total)},
            "tax": {"value": tax, "quote": locale.money(tax) if tax is not None else None},
            "total": {"value": total, "quote": locale.money(total)},
            "payment_method": {
                "value": "Card" if card else "Cash",
                "quote": w["paid_card"] if card else w["paid_cash"],
            },
        },
    }
    return html, truth


def _render_pdf(html: str, receipt: bool) -> bytes:
    pdf = pymupdf.open()
    width, height = (226, 600) if receipt else (595, 842)  # 80 mm till roll / A4
    page = pdf.new_page(width=width, height=height)
    margin = 14 if receipt else 50
    page.insert_htmlbox(pymupdf.Rect(margin, margin, width - margin, height - margin), html)
    pdf.subset_fonts()
    return pdf.tobytes(garbage=4, deflate=True)


def _scan(pdf_bytes: bytes, rng: random.Random) -> bytes:
    """Rasterise like a phone photo or office scanner: lower resolution, slight skew, noise, JPEG."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        pixmap = pdf[0].get_pixmap(dpi=200)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    image = image.rotate(rng.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    noise = Image.effect_noise(image.size, 18).convert("RGB")
    image = Image.blend(image, noise, 0.06)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=72)
    return out.getvalue()


def _check_quotes(name: str, pdf_bytes: bytes, truth: dict) -> None:
    document = load_document(pdf_bytes, "application/pdf", LoadOptions(ocr_enabled=False))
    index = DocumentIndex(document)
    for key, field in truth["fields"].items():
        if field["quote"] is None:
            continue
        anchor = index.locate(field["quote"])
        if anchor is None or anchor.method != "exact":
            raise SystemExit(f"{name}: ground-truth quote for {key!r} not found verbatim: {field['quote']!r}")
        field["page"] = anchor.page + 1


def generate(seed: int = 20261120) -> None:
    rng = random.Random(seed)
    DATASET.mkdir(parents=True, exist_ok=True)
    for old in DATASET.iterdir():
        old.unlink()
    manifest = []
    documents: list[tuple[str, str, dict, bool]] = []
    for n in range(16):
        html, truth = _invoice(rng, n, LOCALES[n % len(LOCALES)])
        documents.append((f"invoice-{n + 1:02d}", html, truth, False))
    for n in range(8):
        html, truth = _receipt(rng, n, LOCALES[n % len(LOCALES)])
        documents.append((f"receipt-{n + 1:02d}", html, truth, True))

    for name, html, truth, receipt in documents:
        pdf_bytes = _render_pdf(html, receipt)
        _check_quotes(name, pdf_bytes, truth)
        (DATASET / f"{name}.pdf").write_bytes(pdf_bytes)
        (DATASET / f"{name}.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
        manifest.append({"name": name, "file": f"{name}.pdf", "kind": "digital", **_meta(truth)})

    # Every fourth document also exists as a scan, which only OCR can read.
    for name, _html, truth, _receipt_flag in documents[::4]:
        scan_name = f"{name}-scan"
        jpeg = _scan((DATASET / f"{name}.pdf").read_bytes(), rng)
        (DATASET / f"{scan_name}.jpg").write_bytes(jpeg)
        scan_truth = {
            **truth,
            "fields": {k: {**v, "page": 1 if v["quote"] else None} for k, v in truth["fields"].items()},
        }
        (DATASET / f"{scan_name}.json").write_text(json.dumps(scan_truth, indent=2, ensure_ascii=False) + "\n")
        manifest.append({"name": scan_name, "file": f"{scan_name}.jpg", "kind": "scan", **_meta(truth)})

    (DATASET / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} documents to {DATASET}")


def _meta(truth: dict) -> dict:
    return {"template": truth["template"], "locale": truth["locale"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=20261120)
    generate(parser.parse_args().seed)
