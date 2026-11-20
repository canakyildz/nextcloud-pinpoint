# Changelog

All notable changes to Pinpoint are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## 0.1.0 – unreleased

### Added
- Extract fields from PDFs and images (scans and photos via Tesseract) into a Nextcloud Tables table,
  using the table's columns as the schema, or from invoice and receipt templates.
- Every value is checked against the document: the model must quote the text it read; the quote is
  located in the document's own word positions and the value must agree with it. Statuses: verified,
  check, not found, empty.
- Cross-field checks: net amount + tax = total, due date not before issue date, required columns.
- Review screen with each value highlighted on its page; nothing is saved before a person approves.
- Saved rows carry a Source link and an Evidence column (page and exact text per value).
- "Extract fields" action in Files, notifications when a document is ready.
- "Extract fields from a document" task type for the Nextcloud Assistant (TaskProcessing provider).
- Admin settings: page limit, file size limit, OCR languages, model timeout, retention.
- Evaluation set of 30 synthetic invoices and receipts (4 languages, scans), an oracle eval with
  injected faults (runs in CI) and a real-model eval.
