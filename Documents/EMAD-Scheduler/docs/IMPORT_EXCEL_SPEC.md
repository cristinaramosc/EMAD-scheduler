# Excel Import Specification

## Scope

This document defines only stage 1 of the EMAD Excel import flow: workbook analysis and validation.

The goal of this stage is to understand the workbook structure and detect the academic entities required for a future importer.

No scheduler objects, persistence, merge logic, or academic-year updates are created in this stage.

## Workbook Structure

The official EMAD workbook is a standard Open XML Excel workbook.

- Supported formats: `.xlsx`, `.xlsm`
- Unsupported for now: `.xls`, `.xlsb`, password-protected workbooks, macro logic, formulas without cached values

The workbook is not a single flat table. It contains multiple worksheet families with different semantics.

Official workbook currently inspected:

- `2627 Validacio jornades CICLES `
- `SUPOSICIONS CICLES`
- `Hoja 4`
- `2425`
- `Copia de curs2324`

These sheets fall into three structural categories:

- Current-year planning matrix sheets: `2627 Validacio jornades CICLES ` and `SUPOSICIONS CICLES`
- Summary sheet: `Hoja 4`
- Historical row-based sheets: `2425` and `Copia de curs2324`

Header matching remains accent-insensitive and case-insensitive, but the official workbook requires sheet-specific parsing strategies rather than a single generic header scan.

## Detected Entities

Stage 1 extracts the following entities without creating scheduler or database records:

- Worksheets: workbook sheet names and per-sheet detection metadata
- Groups: distinct group values found in assignment rows
- Teachers: distinct teacher values found in assignment rows
- Subjects: distinct subject values found in assignment rows
- Teaching assignments: rows where teacher, group, and subject can all be resolved
- Annual hours: numeric values detected either from a dedicated column or from subject labels such as `33h/anuals`, `66h/anuals`, or similar variants

The validation summary reports:

- worksheet count
- teacher count
- group count
- subject count
- teaching assignment count
- annual-hours entry count
- annual-hours total
- warnings
- errors

## Mapping Assumptions

The workbook is the source of truth, but the parser must adapt to the actual EMAD layout families found in the official file.

Current validated assumptions:

- The workbook contains heterogeneous sheets with different import relevance.
- Current-year planning data is encoded as a matrix with hierarchical headers and many merged cells.
- Historical sheets are closer to normalized teaching-assignment tables.
- A valid assignment still requires `teacher`, `group`, and `subject`, but those fields are not always stored on the same row in a flat-table way.
- Annual hours are often embedded inside subject text rather than stored in a dedicated numeric column.
- Rows labelled as totals, subtotals, contract summaries, or coordination summaries must be ignored for assignment detection.
- Carry-forward logic is required for repeated visual blocks where the teacher is only written on the first row of a block.

Assumptions that are no longer valid as written in the first draft:

- Not every worksheet contains a single primary teaching-load table.
- The official workbook cannot be parsed safely through a single generic header-keyword strategy.
- Annual hours cannot be assumed to live in a dedicated `annual_hours` column.

## Fields Intentionally Ignored

The following workbook content is intentionally ignored in stage 1:

- rooms
- weekly timetable placement
- preferred times
- teacher availability
- classroom constraints
- comments and free-form notes
- formulas as business logic for scheduling decisions
- styling, colors, drawings, comments, and formatting beyond what is needed to resolve structural grouping
- academic-year persistence concerns

## Known Limitations

- `.xls` workbooks are not supported yet.
- Only `.xlsx` and `.xlsm` containers are parsed.
- The official workbook includes heavy use of merged cells in the current-year matrix sheets.
- `Hoja 4` contains broken formulas with cached `#REF!` values, so it must be treated as a summary sheet rather than a reliable source for assignments.
- Sheet `2425` is structurally similar to a row-based assignment table, but its subject header is replaced by a year label in the inspected workbook and therefore needs special handling.
- Current-year sheets encode annual hours mainly inside subject labels, so annual-hour extraction must be text-based first and numeric-column-based second.
- Formula cells are only trustworthy when Excel stored a cached value in the file.
- A future importer will need explicit sheet-family classification before entity extraction.

## Proposed Mapping For Next Sprint

Once implementation begins, the importer should first classify each worksheet into one of these families:

- planning matrix sheet
- historical row-based sheet
- summary or non-importable sheet

The normalized intermediate structure should then include at least:

- source worksheet name
- source row number
- source column or column-band identifier when the sheet is matrix-based
- teacher name
- group name
- subject name
- annual hours
- duration or period hint when available
- optional notes or category flags

For current-year matrix sheets, group detection should come from the header hierarchy and teacher detection from the vertical teacher blocks.

For historical row-based sheets, teacher detection should come from the first row of each teacher block and subject detection from the module column.

Only after that intermediate structure is stable should the project map workbook data into scheduler requirements or other domain objects.