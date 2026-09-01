# Consolidated Record — <SUBJECT>

> **Record built from:** `<SOURCE_DIRECTORY>`
> **Pipeline:** OCR-MD-JSON (native PDF text extraction + vision reads + 2-Pass verification).

---

## 1. Identification

| Field | Value |
| --- | --- |
| **Name** | `<SUBJECT NAME>` |
| **Identifier** | `<SUBJECT ID>` *(may appear as multiple/repeated IDs across sources — noted)* |
| **Sex** | `<SEX>` |
| **Date of Birth** | `<DOB>` *(sources may disagree — see note)* |

*(Note: identifier/DOB may differ between source documents; OCR cannot resolve this — needs human confirmation.)*

---

## 2. Imaging & Radiology (chronological)

### 2.x <Study name> — <date>
- **Facility:** `<facility>` | **Exam No:** `<exam no>` | Status: `<status>`
- **Findings:** <findings>
- **Impression:** <impression>

---

## 3. Laboratory Results (chronological)

### 3.x <Panel> — <date> (<lab>)
| Test | Result | Unit | Ref range | Flag |
| --- | --- | --- | --- | --- |
| `<test>` | `<value>` | `<unit>` | `<ref>` | `<flag>` |

---

## 4. Scanned Clinical Documents

### 4.x <Document> — <date>
- <summary / key content>

---

## 5. Administrative Documents

### 5.x <Document> — <date>
- <brief summary>

---

## 6. Source Files Index

| Source file | Type | Content |
| --- | --- | --- |
| `<file>` | `<PDF/image/text>` | `<content>` |

---

## 7. Two-Pass Verification (optional)

| Field | Pass 1 | Pass 2 (independent) | Verdict | Confidence |
| --- | --- | --- | --- | --- |
| `<field>` | `<pass1>` | `<pass2>` | `confirmed/corrected/unresolved` | `high/medium/low` |

---

*Consolidated for `<SUBJECT>` care coordination. This record aggregates the contents of the source folder and does not add medical/clinical interpretation beyond what the source documents state.*
