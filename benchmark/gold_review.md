# Gold review - frozen after user-assisted review

Status: FROZEN. User-assisted review of all 20 questions is recorded in freeze_manifest.json; AI assisted drafting and source checks. No independent verification, reviewer name, signature or approval timestamp is claimed. No retrieval or metrics were run.

English draft from the 40 approved pages. Page numbers below are physical PDF pages; inspect the full source context before approving. Offsets are Unicode [start,end) in normalized text.

## pg16-d01 (dev)

**Question:** Does reading a PostgreSQL table guarantee a fixed row order without an explicit sort?

**Expected answer:** No. Rows appear in an unspecified order unless sorting is explicitly requested.

**Source:** postgresql-16.16-a4; physical page 97; span [886,1066).

**Category/topic:** direct / table_basics.

**Exact evidence:**

```text
SQL does not make any guarantees about
the order of the rows in a table. When a table is read, the rows will appear in an unspecified order,
unless sorting is explicitly requested.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d02 (dev)

**Question:** When is a column default expression evaluated: at table creation or when its default value is inserted?

**Expected answer:** It is evaluated whenever the default value is inserted, not when the table is created.

**Source:** postgresql-16.16-a4; physical page 98; span [2314,2449).

**Category/topic:** paraphrased / defaults.

**Exact evidence:**

```text
The default value can be an expression, which will be evaluated whenever the default value is inserted
(not when the table is created).
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d03 (dev)

**Question:** May a generated-column expression call a non-immutable function or read another row through a subquery?

**Expected answer:** No. It can use only immutable functions and cannot use subqueries or reference anything other than the current row.

**Source:** postgresql-16.16-a4; physical page 99; span [2193,2338).

**Category/topic:** conditional / generated_columns.

**Exact evidence:**

```text
The generation expression can only use immutable functions and cannot use subqueries or reference
anything other than the current row in any way.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d04 (dev)

**Question:** Does CHECK (price > 0) by itself prevent a null price, and what constraint is needed to forbid nulls?

**Expected answer:** No. A CHECK is satisfied by true or null; a not-null constraint is needed to forbid null values.

**Source:** postgresql-16.16-a4; physical page 102; span [605,983).

**Category/topic:** conditional / check_constraints.

**Exact evidence:**

```text
It should be noted that a check constraint is satisfied if the check expression evaluates to true or the
null value. Since most expressions will evaluate to the null value if any operand is null, they will not
prevent null values in the constrained columns. To ensure that a column does not contain null values,
the not-null constraint described in the next section can be used.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d05 (dev)

**Question:** What CHECK expression is functionally equivalent to a not-null constraint, and which form is more efficient in PostgreSQL?

**Expected answer:** CHECK (column_name IS NOT NULL) is functionally equivalent, but an explicit not-null constraint is more efficient.

**Source:** postgresql-16.16-a4; physical page 103; span [1039,1231).

**Category/topic:** paraphrased / not_null.

**Exact evidence:**

```text
A not-null constraint is functionally
equivalent to creating a check constraint CHECK ( column_name IS NOT NULL) , but in
PostgreSQL creating an explicit not-null constraint is more efficient.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d06 (dev)

**Question:** How are two null values treated by default in a unique constraint, and which clause changes that treatment?

**Expected answer:** They are not considered equal by default. NULLS NOT DISTINCT changes that treatment.

**Source:** postgresql-16.16-a4; physical page 104; span [1470,1775).

**Category/topic:** conditional / unique_constraints.

**Exact evidence:**

```text
By default, two null values are not considered
equal in this comparison. That means even in the presence of a unique constraint it is possible to store
duplicate rows that contain a null value in at least one of the constrained columns. This behavior can
be changed by adding the clause NULLS NOT DISTINCT
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d07 (dev)

**Question:** How many primary keys may a table have, and does PostgreSQL require every table to declare one?

**Expected answer:** A table can have at most one primary key. PostgreSQL does not enforce the rule that every table must have one.

**Source:** postgresql-16.16-a4; physical page 105; span [1304,1660).

**Category/topic:** direct / primary_keys.

**Exact evidence:**

```text
A table can have at most one primary key. (There can be any number of unique and not-null constraints,
which are functionally almost the same thing, but only one can be identified as the primary key.)
Relational database theory dictates that every table must have a primary key. This rule is not enforced
by PostgreSQL, but it is usually best to follow it.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d08 (dev)

**Question:** If REFERENCES omits a referenced column list, which columns does PostgreSQL use?

**Expected answer:** It uses the primary key columns of the referenced table.

**Source:** postgresql-16.16-a4; physical page 106; span [1498,1610).

**Category/topic:** direct / foreign_keys.

**Exact evidence:**

```text
because in absence of a column list the primary key of the referenced table is used as the referenced
column(s).
```

**Alternative:** physical page 106; span [177,269).

```text
the primary key defines the default target
column(s) for foreign keys referencing its table.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d09 (dev)

**Question:** What happens to referencing rows when a referenced row is deleted under ON DELETE CASCADE?

**Expected answer:** The rows referencing the deleted row are automatically deleted as well.

**Source:** postgresql-16.16-a4; physical page 108; span [801,920).

**Category/topic:** paraphrased / referential_actions.

**Exact evidence:**

```text
CASCADE specifies that when a referenced row is
deleted, row(s) referencing it should be automatically deleted as well.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d10 (dev)

**Question:** Since PostgreSQL 11, must adding a column with a constant default update every existing row when ALTER TABLE executes?

**Expected answer:** No. Adding a column with a constant default no longer requires updating each row when ALTER TABLE executes.

**Source:** postgresql-16.16-a4; physical page 111; span [374,546).

**Category/topic:** conditional / add_column.

**Exact evidence:**

```text
From PostgreSQL 11, adding a column with a constant default value no longer means that
each row of the table needs to be updated when the ALTER TABLE statement is executed.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d11 (dev)

**Question:** When a dropped column is referenced by a foreign key in another table, does PostgreSQL silently drop that dependency, and how can dependent objects be dropped?

**Expected answer:** It does not silently drop that foreign-key constraint. Adding CASCADE authorizes dropping objects that depend on the column.

**Source:** postgresql-16.16-a4; physical page 111; span [1854,2071).

**Category/topic:** conditional / drop_column.

**Exact evidence:**

```text
However, if the column is referenced by a foreign key constraint of another table, PostgreSQL will
not silently drop that constraint. You can authorize dropping everything that depends on the column
by adding CASCADE:
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d12 (dev)

**Question:** Within Data Definition, how is an unqualified table name resolved through the search path, including when no listed schema matches?

**Expected answer:** The first matching table in the search path is used. If none matches, an error is reported even if the name exists in another schema.

**Source:** postgresql-16.16-a4; physical page 126; span [46,252).

**Category/topic:** section_specific / schema_search_path.

**Supplied filter context:** Pre-retrieval scope supplied by the user: Data Definition

**Filter:** section = Data Definition. The question explicitly requests the Data Definition section; no gold answer or source identifier is used to infer this input.

**Exact evidence:**

```text
The first matching table in the search path is taken to be the one wanted.
If there is no match in the search path, an error is reported, even if matching table names exist in other
schemas in the database.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d13 (dev)

**Question:** For normal access subject to row security, what happens when row-level security is enabled but the table has no policy?

**Expected answer:** A default-deny policy applies: no rows are visible or can be modified.

**Source:** postgresql-16.16-a4; physical page 118; span [1147,1545).

**Category/topic:** conditional / row_security.

**Exact evidence:**

```text
When row security is enabled on a table (with ALTER TABLE ... ENABLE ROW LEVEL
SECURITY), all normal access to the table for selecting rows or modifying rows must be allowed by
a row security policy. (However, the table's owner is typically not subject to row security policies.) If
no policy exists for the table, a default-deny policy is used, meaning that no rows are visible or can
be modified.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d14 (dev)

**Question:** Within Data Manipulation, what fills columns omitted from an INSERT column list?

**Expected answer:** The omitted columns are filled with their default values.

**Source:** postgresql-16.16-a4; physical page 148; span [1690,1830).

**Category/topic:** section_specific / insert.

**Supplied filter context:** Pre-retrieval scope supplied by the user: Data Manipulation

**Filter:** section = Data Manipulation. The question explicitly requests the Data Manipulation section; no gold answer or source identifier is used to infer this input.

**Exact evidence:**

```text
If you don't have values for all the columns, you can omit some of them. In that case, the columns will
be filled with their default values.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-d15 (dev)

**Question:** Which rows are affected by an UPDATE with no WHERE clause compared with an UPDATE that has a WHERE condition?

**Expected answer:** Without WHERE all rows are updated; with WHERE only rows matching its condition are updated.

**Source:** postgresql-16.16-a4; physical page 150; span [152,331).

**Category/topic:** paraphrased / update.

**Exact evidence:**

```text
We also left
out the WHERE clause. If it is omitted, it means that all rows in the table are updated. If it is present,
only those rows that match the WHERE condition are updated.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-t01 (test)

**Question:** How can tableoid be used to obtain the name of the table from which a row originated?

**Expected answer:** Join tableoid against the oid column of pg_class to obtain the table name.

**Source:** postgresql-16.16-a4; physical page 110; span [289,376).

**Category/topic:** direct / system_columns.

**Exact evidence:**

```text
The tableoid can be
joined against the oid column of pg_class to obtain the table name.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-t02 (test)

**Question:** Does a UNIQUE or primary-key constraint on an inheritance parent prevent duplicate key values in its child tables?

**Expected answer:** No. Indexes, including unique constraints, apply to individual tables rather than their inheritance children; parent uniqueness does not prevent such child duplicates.

**Source:** postgresql-16.16-a4; physical page 132; span [16,486).

**Category/topic:** conditional / inheritance.

**Exact evidence:**

```text
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single tables, not to their inheritance children. This is true on both the
referencing and referenced sides of a foreign key constraint. Thus, in the terms of the above example:
• If we declared cities.name to be UNIQUE or a PRIMARY KEY , this would not stop the
capitals table from having rows with names duplicating rows in cities.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-t03 (test)

**Question:** Which table privilege permits executing TRUNCATE?

**Expected answer:** The TRUNCATE privilege permits TRUNCATE on a table.

**Source:** postgresql-16.16-a4; physical page 114; span [2288,2324).

**Category/topic:** direct / privileges.

**Exact evidence:**

```text
TRUNCATE
Allows TRUNCATE on a table.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-t04 (test)

**Question:** Within Data Manipulation, which command should be considered when inserting a large amount of data at once, and how does it compare with INSERT in efficiency and flexibility?

**Expected answer:** Consider COPY. It is more efficient than INSERT, but less flexible.

**Source:** postgresql-16.16-a4; physical page 149; span [558,705).

**Category/topic:** section_specific / bulk_insertion.

**Supplied filter context:** Pre-retrieval scope supplied by the user: Data Manipulation

**Filter:** section = Data Manipulation. The question explicitly requests the Data Manipulation section; no gold answer or source identifier is used to infer this input.

**Exact evidence:**

```text
When inserting a lot of data at the same time, consider using the COPY command. It is not
as flexible as the INSERT command, but is more efficient.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.

## pg16-t05 (test)

**Question:** If triggers are present on the target table, which row contents are made available to RETURNING?

**Expected answer:** RETURNING sees the row as modified by the triggers.

**Source:** postgresql-16.16-a4; physical page 151; span [516,643).

**Category/topic:** conditional / returning_triggers.

**Exact evidence:**

```text
If there are triggers (Chapter 39) on the target table, the data available to RETURNING is the row as
modified by the triggers.
```

**Review provenance:** User-assisted approval recorded in freeze_manifest.json; AI-assisted drafting/source review. Per-record draft fields remain historical provenance, not the effective review state. No independent verification claimed.
