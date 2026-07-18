# Official Workbook Analysis

## Scope

This document records the structural analysis of the official EMAD teaching workload workbook used for academic year 2026-2027.

It is a validation artifact only.

No data has been imported.
No domain objects have been created.
No scheduler logic is involved.

Workbook analysed:

- `data/Validacio_Jornades_2026_2027.xlsx`

## High-Level Conclusion

The workbook is parseable at the file-format level, but it is not yet fully understood at the business-structure level.

The workbook contains three distinct sheet families:

- current-year planning matrix sheets
- summary sheets
- historical row-based sheets

This means the future importer cannot rely on a single generic table parser.

## Worksheets Detected

Five worksheets were detected:

1. `2627 Validacio jornades CICLES `
2. `SUPOSICIONS CICLES`
3. `Hoja 4`
4. `2425`
5. `Copia de curs2324`

## Workbook Structure

### 1. `2627 Validacio jornades CICLES `

- Purpose: current-year validation and workload planning sheet
- Used range: up to column `AQ`
- Non-empty rows: 74
- Merged ranges: 172
- Formula cells: 107

Structure:

- Rows 2 to 4 form a hierarchical header
- Column `A` anchors teacher blocks under `Professorat estable`
- Teaching load is represented horizontally across program and group bands
- Subjects are written as text cells inside the matrix
- Hours are distributed into adjacent quarter columns
- Right-side columns contain coordination, tutoring, lective totals, contract totals, percentage of workload, and difference calculations

Observed header hierarchy in the main teaching area:

- Top level: `COM`, `APGI`, `SUPERIOR`
- Second level: `1r`, `2n`, `1er`, `2n`, `1er COMÚ`, `2n GP`, `2n GI`
- Third level: quarter indicators such as `1Q` and `2Q`

Auxiliary non-assignment columns:

- `COMENTARIS`
- `PFI`
- `Altres`
- `Coordinació`
- `Tutoria`
- `Sindicals`
- `lectives`
- `Preparació`
- `Centre`
- `Suma`
- `Hores contracte`
- `% Jornada`
- `Diferència`
- `Traspàs`

### 2. `SUPOSICIONS CICLES`

- Purpose: alternative or scenario-based planning sheet
- Used range: up to column `AV`
- Non-empty rows: 71
- Merged ranges: 165
- Formula cells: 56

Structure:

- Very similar to `2627 Validacio jornades CICLES `
- Same teacher-block logic in column `A`
- Same horizontal matrix encoding of assignments
- Additional program band detected: `MOB_perfil professional`
- Additional auxiliary columns include `petit EMAD`, `Ajuntament`, `Hores sense assignar`, and contract-summary values

### 3. `Hoja 4`

- Purpose: summary or workload aggregation sheet
- Used range: up to column `M`
- Non-empty rows: 28
- Merged ranges: 147
- Formula cells: 50

Structure:

- This is not a teaching-assignment sheet
- It summarizes workload categories such as `lectives`, `Preparació`, `Centre`, `Suma`, `Hores contracte`, and `% Jornada`
- Teacher names appear in column `A`, but subject and group assignment data does not form an importable table

Critical observation:

- Formula cells such as `H4`, `K4`, and `L10` contain formulas with cached `#REF!` values
- This sheet is not safe as a source for assignment extraction

### 4. `2425`

- Purpose: historical row-based sheet, likely derived from a more normalized teaching-load table
- Used range: up to column `AM`
- Non-empty rows: 164
- Merged ranges: 2
- Formula cells: 52

Structure:

- The sheet is mostly row-based rather than matrix-based
- Teacher information starts in column `B`
- `Curs` and `Cicle` appear as explicit columns
- Weekly hours and duration are explicit numeric/text columns
- Teacher blocks span multiple rows, with continuation rows omitting the teacher name

Critical observation:

- The expected subject column is not explicitly labelled as `Mòduls`
- The inspected header row shows a year-like label `2526` where a subject header would be expected
- This suggests either a template edit, header overwrite, or layout drift compared with older sheets

### 5. `Copia de curs2324`

- Purpose: historical row-based sheet, closer to a canonical import source
- Used range: up to column `AG`
- Non-empty rows: 187
- Merged ranges: 1
- Formula cells: 40

Structure:

- Explicit flat-table style header in row 1
- Main columns:
  - `Professorat estable`
  - `Curs`
  - `Cicle`
  - `Mòduls`
  - `Hores setmanals`
  - `Durada`
  - `relació currículum DEP`
- Teacher blocks span multiple rows and continuation rows leave the teacher cell blank
- This is the clearest reference sheet for normalized row-based parsing

## Merged Cells

Merged-cell usage is significant in the current-year planning sheets and summary sheet:

- `2627 Validacio jornades CICLES `: 172 merged ranges
- `SUPOSICIONS CICLES`: 165 merged ranges
- `Hoja 4`: 147 merged ranges
- `2425`: 2 merged ranges
- `Copia de curs2324`: 1 merged range

Implication:

- A future importer for current-year sheets must resolve merged headers and vertically grouped teacher blocks.
- A plain row-by-row parser without merge awareness will be unreliable.

## Header Hierarchy

### Matrix sheets

The current-year sheets use a three-level header hierarchy:

- Row 2: program family or macro area
- Row 3: course or group band
- Row 4: quarter band or sub-slot

Example hierarchy:

- `COM` -> `1r` -> `1Q`, `2Q`
- `APGI` -> `1er` -> `1Q`, `2Q`
- `SUPERIOR` -> `2n GI` -> `1Q`, `2Q`

The subject label typically appears in the left cell of a band and the numeric quarter values appear in adjacent cells.

### Historical row-based sheets

The historical sheets use a flat header in row 1.

Expected logical columns are:

- teacher
- course
- cycle
- module or subject
- weekly hours
- duration
- supplementary administrative columns

## Teacher Detection Strategy

### Matrix sheets

- Teacher names are anchored in column `A`
- A teacher block begins when column `A` is non-empty
- Continuation rows below the teacher name belong to the same teacher until the next non-empty teacher cell

### Historical row-based sheets

- Teacher appears on the first row of a teacher block
- Subsequent rows may omit the teacher cell and must inherit the previous teacher
- In `2425`, the teacher column is shifted to column `B`

## Group Detection Strategy

### Matrix sheets

- Group is derived from the column hierarchy, not from the data row itself
- A group identifier must be constructed from the program band and the course band
- Quarter labels are important for placement semantics but may not belong in the canonical group identifier

Examples:

- `COM / 1r`
- `APGI / 2n`
- `SUPERIOR / 2n GP`
- `MOB_perfil professional / 1er`

### Historical row-based sheets

- Group-related information is spread across `Curs` and `Cicle`
- The importer will need a normalization rule to decide whether `group` should be `APGI 1`, `1 APGI`, `COMÚ 1`, or another canonical form

## Subject Detection Strategy

### Matrix sheets

- Subjects are free-text labels placed inside teaching bands
- They often include annual-hour information directly in the label
- Examples:
  - `Anglès UF1: Influences today 33h/anuals`
  - `Fotografia UF1 i 2: 66h/anuals`
  - `Dx. Artístic UF1UF2 66h/anuals`

The subject detector must separate:

- display label
- normalized subject or module name
- embedded annual-hours payload

### Historical row-based sheets

- `Copia de curs2324` exposes a dedicated `Mòduls` column
- `2425` appears to store subject-like values in a column whose header is no longer explicit
- `2425` must be treated as structurally ambiguous until that column meaning is confirmed

## Teaching Assignment Detection Strategy

### Matrix sheets

A likely assignment candidate is a text cell that:

- falls inside a teaching-band column family
- belongs to an active teacher block
- contains a module or subject label
- is accompanied by one or more numeric quarter cells nearby

The assignment row is therefore not a flat record. It must be reconstructed from:

- teacher block
- column header hierarchy
- subject text cell
- adjacent numeric workload cells

### Historical row-based sheets

A likely assignment candidate is a row that:

- belongs to an active teacher block
- contains non-empty course or cycle data
- contains non-empty module or subject data
- contains weekly hours and duration or equivalent teaching metadata

## Annual Hours Detection

The workbook uses multiple annual-hour encodings.

### Matrix sheets

Annual hours are usually embedded in the subject label itself.

Examples detected:

- `33h/anuals`
- `66h/anuals`
- `330h/anuals`
- `33+33 h/anuals`

This means annual-hour extraction must parse text, not just numeric columns.

### Historical row-based sheets

- `Copia de curs2324` includes `relació currículum DEP`, which often looks like annual-hour or curriculum-reference data
- `Hores setmanals` and `Durada` may also be enough to infer yearly workload, but this must not be assumed until the business rule is confirmed

## Formulas Found

Formula usage by worksheet:

- `2627 Validacio jornades CICLES `: 107 formula cells
- `SUPOSICIONS CICLES`: 56 formula cells
- `Hoja 4`: 50 formula cells
- `2425`: 52 formula cells
- `Copia de curs2324`: 40 formula cells

Formula roles observed:

- lective-hour totals
- workload sums
- contract-hour differences
- percentage-of-workload calculations

Important risk:

- `Hoja 4` contains cached `#REF!` values and should not be trusted as an import source

## Comparison With `IMPORT_EXCEL_SPEC.md`

The first draft of the spec was only partially correct.

Correct assumptions:

- the workbook is an `.xlsx` file
- carry-forward logic is needed for visually grouped rows
- worksheet-by-worksheet analysis is appropriate

Incorrect or incomplete assumptions:

- the workbook is not a single flat-table family
- annual hours are not primarily stored in a dedicated column
- a single keyword-based header detector is not sufficient
- not every worksheet is importable or even intended as an assignment source

## Potential Ambiguities

The following ambiguities remain open:

- Whether `2627 Validacio jornades CICLES ` or `SUPOSICIONS CICLES` is the authoritative current-year source sheet, or whether both must be combined with precedence rules
- Whether sheet `2425` is intentionally malformed, partially edited, or using a year label in place of a subject header
- Whether quarter labels `1Q` and `2Q` are merely scheduling hints or part of the teaching-assignment identity
- How to normalize group names across matrix sheets and historical sheets into a stable canonical identifier
- Whether labels such as `LL.Disp`, `Tutoria`, `Coordinació`, `FCT`, and `petit EMAD` should all be imported as teaching assignments or split into separate categories
- Whether values like `33+33 h/anuals` represent one assignment, two linked assignments, or one grouped subject with multiple units
- Whether `330h/anuals` and similar labels should be interpreted literally or normalized through curriculum rules
- Whether `relació currículum DEP` is a curriculum-reference field, an annual-hours field, or a mixed historical artifact
- Whether summary-side columns such as `Altres`, `Coordinació`, `Tutoria`, and `Sindicals` belong in the future importer scope

## Potential Import Risks

- Misclassifying summary columns as teaching assignments
- Double counting assignments when the same subject appears across multiple quarter columns
- Losing group meaning if merged-header resolution is incomplete
- Incorrectly inheriting teacher names across continuation rows
- Treating administrative workload entries as teachable modules
- Deriving annual hours incorrectly from text labels with compound expressions
- Depending on formula results that are summary-only or broken
- Overfitting the parser to the current workbook wording instead of the layout family

## Current Readiness Assessment

The workbook is parseable as an Excel file, but not yet fully understood as an import source.

It is safe to continue with a next sprint only if implementation starts by clarifying the remaining ambiguities above and by defining explicit sheet-family rules before any domain import is attempted.