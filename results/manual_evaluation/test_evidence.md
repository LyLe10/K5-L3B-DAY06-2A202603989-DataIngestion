# TEST evidence and actual top-3 retrieval

Source: test-001, COMPLETE. Source facts only; human review pending. See NOTICE.txt. Similarity and exact metrics are in retrieval_metrics.csv / retrieval_traces.jsonl; they do not determine human labels.

## pg16-t01

Question: How can tableoid be used to obtain the name of the table from which a row originated?

Expected answer: Join tableoid against the oid column of pg_class to obtain the table name.

Question/context filter: `null`

Gold 0: `postgresql-16.16-a4`, physical page 110, printed page 72, offsets [289,376).

```text
The tableoid can be
joined against the oid column of pg_class to obtain the table name.
```

### pg16-t01-A

Trace SHA-256: `0ac476eb0032be6c0b26f92979ebffd319f2147030e1aa624d26227197da0e34`

Applied filter: `null`

#### Rank 1: `A:bf00b62010edf280aa923b5aa4e11f156b49e5b18292a21c5719efec495320f9`

Physical page 110; printed page 72; section `Data Definition`; offsets [0,500).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 110: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) 
```

Retrieved chunk (verbatim):

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) or inheritance hierarchies (see Section 5.10 ), since
without it, it's difficult to tell which individual table a row came from. The tableoid can be
joined against the oid column of pg_class to obtain the table name.
xmin
The identity (transaction ID) of the inserting transaction for this row version. (A row version is an
individual state
```

#### Rank 2: `A:6261365cf339cbd013514f49db948d62c0b6c1ab04729f89202eec33a0c1bd6e`

Physical page 130; printed page 92; section `Data Definition`; offsets [0,500).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
supported for compatibility with older releases where the default could be changed.
In some cases you might wish to know which table a particular row originated from. There is a system
column called tableoid in each table which can tell you the originating table:
SELECT c.tableoid, c.name, c.elevation
FROM cities c
WHERE c.elevation > 500;
which
```

#### Rank 3: `A:896d0f1490ab525229732e2db6a11bab70cffabedbade1c695f7227341cf0cb5`

Physical page 130; printed page 92; section `Data Definition`; offsets [450,950).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
ation
FROM cities c
WHERE c.elevation > 500;
which returns:
tableoid | name | elevation
----------+-----------+-----------
139793 | Las Vegas | 2174
139793 | Mariposa | 1953
139798 | Madison | 845
(If you try to reproduce this example, you will probably get different numeric OIDs.) By doing a join
with pg_class you can see the actual table names:
SELECT p.relname, c.name, c.elevation
FROM cities c, pg_class p
WHERE c.elevation > 500 AND c.tableoid = p.oid;
which returns:
relname | name | elevati
```

### pg16-t01-B

Trace SHA-256: `e6abd4972bb141d34da53d91a216a5d2a28999987417765d09cd84499eab3455`

Applied filter: `null`

#### Rank 1: `B:1287278612053429725298200b0df5bf16297db221658c047a90f7e7f8dd95e5`

Physical page 110; printed page 72; section `Data Definition`; offsets [0,463).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 110: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) 
```

Retrieved chunk (verbatim):

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) or inheritance hierarchies (see Section 5.10 ), since
without it, it's difficult to tell which individual table a row came from. The tableoid can be
joined against the oid column of pg_class to obtain the table name.
xmin
The identity (transaction ID) of the inserting transaction for this row version. 
```

#### Rank 2: `B:c5de582c817ecd9632c9023b91eb0fc71b702c0bd1662dfc028f5256c4055574`

Physical page 130; printed page 92; section `Data Definition`; offsets [320,799).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
There is a system
column called tableoid in each table which can tell you the originating table:
SELECT c.tableoid, c.name, c.elevation
FROM cities c
WHERE c.elevation > 500;
which returns:
tableoid | name | elevation
----------+-----------+-----------
139793 | Las Vegas | 2174
139793 | Mariposa | 1953
139798 | Madison | 845
(If you try to reproduce this example, you will probably get different numeric OIDs.) By doing a join
with pg_class you can see the actual table names:

```

#### Rank 3: `B:611f09115ed9432642ea02546f1bab750d725268bebc368198596a0c481216df`

Physical page 130; printed page 92; section `Data Definition`; offsets [799,1267).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
SELECT p.relname, c.name, c.elevation
FROM cities c, pg_class p
WHERE c.elevation > 500 AND c.tableoid = p.oid;
which returns:
relname | name | elevation
----------+-----------+-----------
cities | Las Vegas | 2174
cities | Mariposa | 1953
capitals | Madison | 845
Another way to get the same effect is to use the regclass alias type, which will print the table OID
symbolically:
SELECT c.tableoid::regclass, c.name, c.elevation
FROM cities c
WHERE c.elevation > 500;

```

### pg16-t01-C

Trace SHA-256: `f35609fb41c8fea11044b6460b134fb31a49a89e90468cbe0c24d284b96c2fc9`

Applied filter: `null`

#### Rank 1: `B:1287278612053429725298200b0df5bf16297db221658c047a90f7e7f8dd95e5`

Physical page 110; printed page 72; section `Data Definition`; offsets [0,463).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 110: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) 
```

Retrieved chunk (verbatim):

```text
Data Definition
The OID of the table containing this row. This column is particularly handy for queries that select
from partitioned tables (see Section 5.11 ) or inheritance hierarchies (see Section 5.10 ), since
without it, it's difficult to tell which individual table a row came from. The tableoid can be
joined against the oid column of pg_class to obtain the table name.
xmin
The identity (transaction ID) of the inserting transaction for this row version. 
```

#### Rank 2: `B:c5de582c817ecd9632c9023b91eb0fc71b702c0bd1662dfc028f5256c4055574`

Physical page 130; printed page 92; section `Data Definition`; offsets [320,799).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
There is a system
column called tableoid in each table which can tell you the originating table:
SELECT c.tableoid, c.name, c.elevation
FROM cities c
WHERE c.elevation > 500;
which returns:
tableoid | name | elevation
----------+-----------+-----------
139793 | Las Vegas | 2174
139793 | Mariposa | 1953
139798 | Madison | 845
(If you try to reproduce this example, you will probably get different numeric OIDs.) By doing a join
with pg_class you can see the actual table names:

```

#### Rank 3: `B:611f09115ed9432642ea02546f1bab750d725268bebc368198596a0c481216df`

Physical page 130; printed page 92; section `Data Definition`; offsets [799,1267).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
SELECT p.relname, c.name, c.elevation
FROM cities c, pg_class p
WHERE c.elevation > 500 AND c.tableoid = p.oid;
which returns:
relname | name | elevation
----------+-----------+-----------
cities | Las Vegas | 2174
cities | Mariposa | 1953
capitals | Madison | 845
Another way to get the same effect is to use the regclass alias type, which will print the table OID
symbolically:
SELECT c.tableoid::regclass, c.name, c.elevation
FROM cities c
WHERE c.elevation > 500;

```

## pg16-t02

Question: Does a UNIQUE or primary-key constraint on an inheritance parent prevent duplicate key values in its child tables?

Expected answer: No. Indexes, including unique constraints, apply to individual tables rather than their inheritance children; parent uniqueness does not prevent such child duplicates.

Question/context filter: `null`

Gold 0: `postgresql-16.16-a4`, physical page 132, printed page 94, offsets [16,486).

```text
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single tables, not to their inheritance children. This is true on both the
referencing and referenced sides of a foreign key constraint. Thus, in the terms of the above example:
• If we declared cities.name to be UNIQUE or a PRIMARY KEY , this would not stop the
capitals table from having rows with names duplicating rows in cities.
```

### pg16-t02-A

Trace SHA-256: `6cb4e0a357221ba3cb5a46277f52f34f6667eb52d4ca285aaeed0e9a9238ed2f`

Applied filter: `null`

#### Rank 1: `A:22c3f31b59614bc31afee391bb77d8640be793b2770c312522e8e6e23dbb8ead`

Physical page 132; printed page 94; section `Data Definition`; offsets [0,500).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 132: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single 
```

Retrieved chunk (verbatim):

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single tables, not to their inheritance children. This is true on both the
referencing and referenced sides of a foreign key constraint. Thus, in the terms of the above example:
• If we declared cities.name to be UNIQUE or a PRIMARY KEY , this would not stop the
capitals table from having rows with names duplicating rows in cities. And those dup
```

#### Rank 2: `A:61dc5ec7625a289c2754ebc6a6c140f0ca377aa99a6a8be4dc6493fc2bf7cf89`

Physical page 131; printed page 93; section `Data Definition`; offsets [0,500).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 131: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherw
```

Retrieved chunk (verbatim):

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherwise with NO INHERIT clauses. Other types of constraints
(unique, primary key, and foreign key constraints) are not inherited.
A table can inherit from more than one parent table, in which case it has the union of the columns
defined by the parent tables. Any columns declared in the child table's definition are added to these.
If the same 
```

#### Rank 3: `A:ad73b315745c2a09715de427e8aa6bb797c825f0fea42199d38a92b11342f49d`

Physical page 102; printed page 64; section `Data Definition`; offsets [1350,1850).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 102: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
discounted_price numeric,
CHECK (discounted_price > 0),
CHECK (price > discounted_price)
);
or even:
CREATE TABLE products (
product_no integer,
```

Retrieved chunk (verbatim):

```text
lved). This
would cause a database dump and restore to fail. The restore could fail even when the complete
database state is consistent with the constraint, due to rows not being loaded in an order that
will satisfy the constraint. If possible, use UNIQUE, EXCLUDE, or FOREIGN KEY constraints
to express cross-row and cross-table restrictions.
If what you desire is a one-time check against other rows at row insertion, rather than a
continuously-maintained consistency guarantee, a custom trigger ca
```

### pg16-t02-B

Trace SHA-256: `b1d5dcd44aa6383eaa0ca134cb693980a47d13d69d5567d2509c3598e3a325c4`

Applied filter: `null`

#### Rank 1: `B:2cfc629aa72b73e841f031206fb9824c568d486b2ae14d9c964129201b0cae7f`

Physical page 132; printed page 94; section `Data Definition`; offsets [0,487).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 132: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single 
```

Retrieved chunk (verbatim):

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single tables, not to their inheritance children. This is true on both the
referencing and referenced sides of a foreign key constraint. Thus, in the terms of the above example:
• If we declared cities.name to be UNIQUE or a PRIMARY KEY , this would not stop the
capitals table from having rows with names duplicating rows in cities. 
```

#### Rank 2: `B:4a6ea6c6acdfe00b32a001b8d9e415c59f6afc60090bd5f20600d47574e5ab4f`

Physical page 104; printed page 66; section `Data Definition`; offsets [1306,1707).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 104: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
5.4.3. Unique Constraints
Unique constraints ensure that the data contained in a column, or a group of columns, is unique among
all the rows in 
```

Retrieved chunk (verbatim):

```text
In general, a unique constraint is violated if there is more than one row in the table where the values of
all of the columns included in the constraint are equal. By default, two null values are not considered
equal in this comparison. That means even in the presence of a unique constraint it is possible to store
duplicate rows that contain a null value in at least one of the constrained columns. 
```

#### Rank 3: `B:0957a0b599ede12d71d55bbcf5777d98f89f9ee1427f2be8758cc7c66ae236b7`

Physical page 131; printed page 93; section `Data Definition`; offsets [0,488).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 131: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherw
```

Retrieved chunk (verbatim):

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherwise with NO INHERIT clauses. Other types of constraints
(unique, primary key, and foreign key constraints) are not inherited.
A table can inherit from more than one parent table, in which case it has the union of the columns
defined by the parent tables. Any columns declared in the child table's definition are added to these.

```

### pg16-t02-C

Trace SHA-256: `674f08b9947f69fcf78a5e9a3128af9707a6f66a4e09a29107c700c06a0d8b27`

Applied filter: `null`

#### Rank 1: `B:2cfc629aa72b73e841f031206fb9824c568d486b2ae14d9c964129201b0cae7f`

Physical page 132; printed page 94; section `Data Definition`; offsets [0,487).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 132: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single 
```

Retrieved chunk (verbatim):

```text
Data Definition
A serious limitation of the inheritance feature is that indexes (including unique constraints) and foreign
key constraints only apply to single tables, not to their inheritance children. This is true on both the
referencing and referenced sides of a foreign key constraint. Thus, in the terms of the above example:
• If we declared cities.name to be UNIQUE or a PRIMARY KEY , this would not stop the
capitals table from having rows with names duplicating rows in cities. 
```

#### Rank 2: `B:4a6ea6c6acdfe00b32a001b8d9e415c59f6afc60090bd5f20600d47574e5ab4f`

Physical page 104; printed page 66; section `Data Definition`; offsets [1306,1707).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 104: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
5.4.3. Unique Constraints
Unique constraints ensure that the data contained in a column, or a group of columns, is unique among
all the rows in 
```

Retrieved chunk (verbatim):

```text
In general, a unique constraint is violated if there is more than one row in the table where the values of
all of the columns included in the constraint are equal. By default, two null values are not considered
equal in this comparison. That means even in the presence of a unique constraint it is possible to store
duplicate rows that contain a null value in at least one of the constrained columns. 
```

#### Rank 3: `B:0957a0b599ede12d71d55bbcf5777d98f89f9ee1427f2be8758cc7c66ae236b7`

Physical page 131; printed page 93; section `Data Definition`; offsets [0,488).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 131: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherw
```

Retrieved chunk (verbatim):

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherwise with NO INHERIT clauses. Other types of constraints
(unique, primary key, and foreign key constraints) are not inherited.
A table can inherit from more than one parent table, in which case it has the union of the columns
defined by the parent tables. Any columns declared in the child table's definition are added to these.

```

## pg16-t03

Question: Which table privilege permits executing TRUNCATE?

Expected answer: The TRUNCATE privilege permits TRUNCATE on a table.

Question/context filter: `null`

Gold 0: `postgresql-16.16-a4`, physical page 114, printed page 76, offsets [2288,2324).

```text
TRUNCATE
Allows TRUNCATE on a table.
```

### pg16-t03-A

Trace SHA-256: `98c9e572b4f004ad289970e677cee22bc6af7548ce3826fd31821de6e92a610e`

Applied filter: `null`

#### Rank 1: `A:87ce08debdb5fe1c6645a5b768c5dacba171abdf285e28b8ab9c0ffd9cb4d462`

Physical page 114; printed page 76; section `Data Definition`; offsets [2250,2750).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 114: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
To revoke a previously-granted privilege, use the fittingly named REVOKE command:
REVOKE ALL ON accounts FROM PUBLIC;
Ordinarily, only the objec
```

Retrieved chunk (verbatim):

```text
s to determine which
rows to delete.)
TRUNCATE
Allows TRUNCATE on a table.
REFERENCES
Allows creation of a foreign key constraint referencing a table, or specific column(s) of a table.
Great care should be taken when granting this privilege, since a user who creates a foreign key can
arrange for enforcement of that foreign key to call an arbitrary function, such as a cast function,
and such functions will be called with the privileges of the table owner.
TRIGGER
Allows creation of a trigger on a
```

#### Rank 2: `A:a5e07efff1f6b6a2b21ff562436d1ae99beea036aa94a16f577b69a40665036e`

Physical page 113; printed page 75; section `Data Definition`; offsets [900,1400).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 113: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
This will succeed only if each existing entry in the column can be converted to the new type by an
implicit cast. If a more complex conversion i
```

Retrieved chunk (verbatim):

```text
t executed the
creation statement. For most kinds of objects, the initial state is that only the owner (or a superuser)
can do anything with the object. To allow other roles to use it, privileges must be granted.
There are different kinds of privileges: SELECT, INSERT, UPDATE, DELETE, TRUNCATE,
REFERENCES, TRIGGER, CREATE, CONNECT, TEMPORARY, EXECUTE, USAGE, SET and ALTER
SYSTEM. The privileges applicable to a particular object vary depending on the object's type (table,
function, etc.). More de
```

#### Rank 3: `A:15bd51d670cad90c7c59f09116468d1381421267eeb896af73165912a98eb5ce`

Physical page 114; printed page 76; section `Data Definition`; offsets [1800,2300).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 114: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
To revoke a previously-granted privilege, use the fittingly named REVOKE command:
REVOKE ALL ON accounts FROM PUBLIC;
Ordinarily, only the objec
```

Retrieved chunk (verbatim):

```text
R UPDATE and SELECT ... FOR SHARE also require this privilege on
at least one column, in addition to the SELECT privilege. For sequences, this privilege allows
use of the nextval and setval functions. For large objects, this privilege allows writing or
truncating the object.
DELETE
Allows DELETE of a row from a table, view, etc. (In practice, any nontrivial DELETE command
will require SELECT privilege as well, since it must reference table columns to determine which
rows to delete.)
TRUNCATE
All
```

### pg16-t03-B

Trace SHA-256: `c5333ff6533e36ec974aa31ee5744211f0b0b30cddc320dcb875c3387690c178`

Applied filter: `null`

#### Rank 1: `B:85ed0d9c9b2e00ceb52fd9387f6e9c6facfc9b0bfeeb01d1e5237dec45dc79f1`

Physical page 114; printed page 76; section `Data Definition`; offsets [2131,2435).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 114: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
To revoke a previously-granted privilege, use the fittingly named REVOKE command:
REVOKE ALL ON accounts FROM PUBLIC;
Ordinarily, only the objec
```

Retrieved chunk (verbatim):

```text
(In practice, any nontrivial DELETE command
will require SELECT privilege as well, since it must reference table columns to determine which
rows to delete.)
TRUNCATE
Allows TRUNCATE on a table.
REFERENCES
Allows creation of a foreign key constraint referencing a table, or specific column(s) of a table.

```

#### Rank 2: `B:edda6c3a707f394c92a89fde185cbad9451fcc247a52bb9b9e317fd85b8a0555`

Physical page 113; printed page 75; section `Data Definition`; offsets [935,1393).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 113: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
This will succeed only if each existing entry in the column can be converted to the new type by an
implicit cast. If a more complex conversion i
```

Retrieved chunk (verbatim):

```text
For most kinds of objects, the initial state is that only the owner (or a superuser)
can do anything with the object. To allow other roles to use it, privileges must be granted.
There are different kinds of privileges: SELECT, INSERT, UPDATE, DELETE, TRUNCATE,
REFERENCES, TRIGGER, CREATE, CONNECT, TEMPORARY, EXECUTE, USAGE, SET and ALTER
SYSTEM. The privileges applicable to a particular object vary depending on the object's type (table,
function, etc.). 
```

#### Rank 3: `B:24c28a9f9e616c279ae54114caa0d93e54d4eca7c8935365119eaa64a9df8738`

Physical page 115; printed page 77; section `Data Definition`; offsets [346,799).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 115: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
CREATE
For databases, allows new schemas and publications to be created within the database, and allows
trusted extensions to be installed withi
```

Retrieved chunk (verbatim):

```text
For tablespaces, allows tables, indexes, and temporary files to be created within the tablespace,
and allows databases to be created that have the tablespace as their default tablespace.
Note that revoking this privilege will not alter the existence or location of existing objects.
CONNECT
Allows the grantee to connect to the database. This privilege is checked at connection startup (in
addition to checking any restrictions imposed by pg_hba.conf).

```

### pg16-t03-C

Trace SHA-256: `b4efc33e3bf0b4bb954252efb2daae4bf9da43dbdb33d8505be7893525f1364c`

Applied filter: `null`

#### Rank 1: `B:85ed0d9c9b2e00ceb52fd9387f6e9c6facfc9b0bfeeb01d1e5237dec45dc79f1`

Physical page 114; printed page 76; section `Data Definition`; offsets [2131,2435).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 114: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
To revoke a previously-granted privilege, use the fittingly named REVOKE command:
REVOKE ALL ON accounts FROM PUBLIC;
Ordinarily, only the objec
```

Retrieved chunk (verbatim):

```text
(In practice, any nontrivial DELETE command
will require SELECT privilege as well, since it must reference table columns to determine which
rows to delete.)
TRUNCATE
Allows TRUNCATE on a table.
REFERENCES
Allows creation of a foreign key constraint referencing a table, or specific column(s) of a table.

```

#### Rank 2: `B:edda6c3a707f394c92a89fde185cbad9451fcc247a52bb9b9e317fd85b8a0555`

Physical page 113; printed page 75; section `Data Definition`; offsets [935,1393).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 113: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
This will succeed only if each existing entry in the column can be converted to the new type by an
implicit cast. If a more complex conversion i
```

Retrieved chunk (verbatim):

```text
For most kinds of objects, the initial state is that only the owner (or a superuser)
can do anything with the object. To allow other roles to use it, privileges must be granted.
There are different kinds of privileges: SELECT, INSERT, UPDATE, DELETE, TRUNCATE,
REFERENCES, TRIGGER, CREATE, CONNECT, TEMPORARY, EXECUTE, USAGE, SET and ALTER
SYSTEM. The privileges applicable to a particular object vary depending on the object's type (table,
function, etc.). 
```

#### Rank 3: `B:24c28a9f9e616c279ae54114caa0d93e54d4eca7c8935365119eaa64a9df8738`

Physical page 115; printed page 77; section `Data Definition`; offsets [346,799).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 115: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
CREATE
For databases, allows new schemas and publications to be created within the database, and allows
trusted extensions to be installed withi
```

Retrieved chunk (verbatim):

```text
For tablespaces, allows tables, indexes, and temporary files to be created within the tablespace,
and allows databases to be created that have the tablespace as their default tablespace.
Note that revoking this privilege will not alter the existence or location of existing objects.
CONNECT
Allows the grantee to connect to the database. This privilege is checked at connection startup (in
addition to checking any restrictions imposed by pg_hba.conf).

```

## pg16-t04

Question: Within Data Manipulation, which command should be considered when inserting a large amount of data at once, and how does it compare with INSERT in efficiency and flexibility?

Expected answer: Consider COPY. It is more efficient than INSERT, but less flexible.

Question/context filter: `{"section": "Data Manipulation"}`

Gold 0: `postgresql-16.16-a4`, physical page 149, printed page 111, offsets [558,705).

```text
When inserting a lot of data at the same time, consider using the COPY command. It is not
as flexible as the INSERT command, but is more efficient.
```

### pg16-t04-A

Trace SHA-256: `767bcc4ffb7de7855dc49b9d35c0f67f6852b64ce9cba0f67779a76a5992d09d`

Applied filter: `null`

#### Rank 1: `A:d04fa628d4b70311d5e0d9419a903e034430411895dc8cfcd58f60618823ef9f`

Physical page 149; printed page 111; section `Data Manipulation`; offsets [450,950).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 149: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO products DEFAULT VALUES;
You can insert multiple rows in a single command:
INSERT INTO products (product_no, name, price) VALUES
(
```

Retrieved chunk (verbatim):

```text
 provides the full power of the SQL query mechanism ( Chapter 7) for computing the rows to be
inserted.
Tip
When inserting a lot of data at the same time, consider using the COPY command. It is not
as flexible as the INSERT command, but is more efficient. Refer to Section 14.4 for more
information on improving bulk loading performance.
6.2. Updating Data
The modification of data that is already in the database is referred to as updating. You can update
individual rows, all the rows in a table, o
```

#### Rank 2: `A:4af7172d083457cb2642615f87ad4b6060418b70f5a7bfe5aaf1dbc72b9d2d19`

Physical page 114; printed page 76; section `Data Definition`; offsets [900,1400).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 114: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
To revoke a previously-granted privilege, use the fittingly named REVOKE command:
REVOKE ALL ON accounts FROM PUBLIC;
Ordinarily, only the objec
```

Retrieved chunk (verbatim):

```text
mn, or specific column(s), of a table, view, materialized view, or
other table-like object. Also allows use of COPY TO. This privilege is also needed to reference
existing column values in UPDATE, DELETE, or MERGE. For sequences, this privilege also allows
use of the currval function. For large objects, this privilege allows the object to be read.
INSERT
Allows INSERT of a new row into a table, view, etc. Can be granted on specific column(s), in
which case only those columns may be assigned to i
```

#### Rank 3: `A:0ccf57229dfa2ed3b8e5978a171d1058af3978f608d7d72826dc14152fd7afd8`

Physical page 131; printed page 93; section `Data Definition`; offsets [4050,4550).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 131: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
All check constraints and not-null constraints on a parent table are automatically inherited by its
children, unless explicitly specified otherw
```

Retrieved chunk (verbatim):

```text
 work on inheritance hierarchies. Commands that are used
for data querying, data modification, or schema modification (e.g., SELECT, UPDATE, DELETE, most
variants of ALTER TABLE, but not INSERT or ALTER TABLE ... RENAME ) typically default
to including child tables and support the ONLY notation to exclude them. Commands that do database
maintenance and tuning (e.g., REINDEX, VACUUM) typically only work on individual, physical tables
and do not support recursing over inheritance hierarchies. The 
```

### pg16-t04-B

Trace SHA-256: `b3dfd42c54aa25e6348a71a3a5ae07cae12187b6a18774af04919d0475cde4d3`

Applied filter: `null`

#### Rank 1: `B:750ae314e501bc85b0c1f3e5411298d97628c2c9adb22448bdd1fe24dc8977e0`

Physical page 149; printed page 111; section `Data Manipulation`; offsets [446,892).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 149: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO products DEFAULT VALUES;
You can insert multiple rows in a single command:
INSERT INTO products (product_no, name, price) VALUES
(
```

Retrieved chunk (verbatim):

```text
This provides the full power of the SQL query mechanism ( Chapter 7) for computing the rows to be
inserted.
Tip
When inserting a lot of data at the same time, consider using the COPY command. It is not
as flexible as the INSERT command, but is more efficient. Refer to Section 14.4 for more
information on improving bulk loading performance.
6.2. Updating Data
The modification of data that is already in the database is referred to as updating. 
```

#### Rank 2: `B:0b747a57c6fa2087b0c31e8c9375f420c908135dd2502a829b7de40e82083c36`

Physical page 148; printed page 110; section `Data Manipulation`; offsets [474,814).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 148: chapter heading or running header

Source page heading excerpt:

```text
Chapter 6. Data Manipulation
The previous chapter discussed how to create tables and other structures to hold your data. Now it is
time to fill the tables with 
```

Retrieved chunk (verbatim):

```text
Data is inserted one row at a time. You can also insert more than one row in a single
command, but it is not possible to insert something that is not a complete row. Even if you know only
some column values, a complete row must be created.
To create a new row, use the INSERT command. The command requires the table name and column
values. 
```

#### Rank 3: `B:b19a6a6451c622a1a83656410ecf26665c940b83de2ad5efca7c356fb627376f`

Physical page 130; printed page 92; section `Data Definition`; offsets [1267,1700).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 97: chapter heading; page 130: chapter heading or running header

Source page heading excerpt:

```text
Data Definition
FROM cities*
WHERE elevation > 500;
Writing * is not necessary, since this behavior is always the default. However, this syntax is still
support
```

Retrieved chunk (verbatim):

```text
Inheritance does not automatically propagate data from INSERT or COPY commands to other tables
in the inheritance hierarchy. In our example, the following INSERT statement will fail:
INSERT INTO cities (name, population, elevation, state)
VALUES ('Albany', NULL, NULL, 'NY');
We might hope that the data would somehow be routed to the capitals table, but this does not
happen: INSERT always inserts into exactly the table specified. 
```

### pg16-t04-C

Trace SHA-256: `0319e99ded904bc80a77c616646a2b4617b187387819ae25e9b5b0e52be0d94f`

Applied filter: `{"section": "Data Manipulation"}`

#### Rank 1: `B:750ae314e501bc85b0c1f3e5411298d97628c2c9adb22448bdd1fe24dc8977e0`

Physical page 149; printed page 111; section `Data Manipulation`; offsets [446,892).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 149: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO products DEFAULT VALUES;
You can insert multiple rows in a single command:
INSERT INTO products (product_no, name, price) VALUES
(
```

Retrieved chunk (verbatim):

```text
This provides the full power of the SQL query mechanism ( Chapter 7) for computing the rows to be
inserted.
Tip
When inserting a lot of data at the same time, consider using the COPY command. It is not
as flexible as the INSERT command, but is more efficient. Refer to Section 14.4 for more
information on improving bulk loading performance.
6.2. Updating Data
The modification of data that is already in the database is referred to as updating. 
```

#### Rank 2: `B:0b747a57c6fa2087b0c31e8c9375f420c908135dd2502a829b7de40e82083c36`

Physical page 148; printed page 110; section `Data Manipulation`; offsets [474,814).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 148: chapter heading or running header

Source page heading excerpt:

```text
Chapter 6. Data Manipulation
The previous chapter discussed how to create tables and other structures to hold your data. Now it is
time to fill the tables with 
```

Retrieved chunk (verbatim):

```text
Data is inserted one row at a time. You can also insert more than one row in a single
command, but it is not possible to insert something that is not a complete row. Even if you know only
some column values, a complete row must be created.
To create a new row, use the INSERT command. The command requires the table name and column
values. 
```

#### Rank 3: `B:9abf7fda00cc6bc972075f950b65feaf6b9b822e5e39d2aba8327a514f9e8cce`

Physical page 149; printed page 111; section `Data Manipulation`; offsets [0,446).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 149: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO products DEFAULT VALUES;
You can insert multiple rows in a single command:
INSERT INTO products (product_no, name, price) VALUES
(
```

Retrieved chunk (verbatim):

```text
Data Manipulation
INSERT INTO products DEFAULT VALUES;
You can insert multiple rows in a single command:
INSERT INTO products (product_no, name, price) VALUES
(1, 'Cheese', 9.99),
(2, 'Bread', 1.99),
(3, 'Milk', 2.99);
It is also possible to insert the result of a query (which might be no rows, one row, or many rows):
INSERT INTO products (product_no, name, price)
SELECT product_no, name, price FROM new_products
WHERE release_date = 'today';

```

## pg16-t05

Question: If triggers are present on the target table, which row contents are made available to RETURNING?

Expected answer: RETURNING sees the row as modified by the triggers.

Question/context filter: `null`

Gold 0: `postgresql-16.16-a4`, physical page 151, printed page 113, offsets [516,643).

```text
If there are triggers (Chapter 39) on the target table, the data available to RETURNING is the row as
modified by the triggers.
```

### pg16-t05-A

Trace SHA-256: `7a564ad69f4c46739ac700a1286e1e5d14cfa6d4db3525087950ee757b6c86d7`

Applied filter: `null`

#### Rank 1: `A:352ebebb9661264bdfa19a766fef19e48ce8680d9a4b10923ee9eb9f1adfe51c`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [2250,2750).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
wed contents of a RETURNING clause are the same as a SELECT command's output list (see
Section 7.3). It can contain column names of the command's target table, or value expressions using
those columns. A common shorthand is RETURNING *, which selects all columns of the target table
in order.
In an INSERT, the data available to RETURNING is the row as it was inserted. This is not so useful in
trivial inserts, since it would just repeat the data provided by the client. But it can be very handy whe
```

#### Rank 2: `A:6012482775c19775dde22e7799e0d842f236ba1811e87e0e2a5ead3458ee8b8d`

Physical page 151; printed page 113; section `Data Manipulation`; offsets [450,735).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 151: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO users (firstname, lastname) VALUES ('Joe', 'Cool')
RETURNING id;
The RETURNING clause is also very useful with INSERT ... SELECT.

```

Retrieved chunk (verbatim):

```text
DELETE FROM products
WHERE obsoletion_date = 'today'
RETURNING *;
If there are triggers (Chapter 39) on the target table, the data available to RETURNING is the row as
modified by the triggers. Thus, inspecting columns computed by triggers is another common use-case
for RETURNING.
113
```

#### Rank 3: `A:42b2d662e71559c3a2f8a4a3d7e559f8f8c3f6f35ca44e62f7ed776bd547a323`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [2700,2988).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
ovided by the client. But it can be very handy when
relying on computed default values. For example, when using a serial column to provide unique
identifiers, RETURNING can return the ID assigned to a new row:
CREATE TABLE users (firstname text, lastname text, id serial
primary key);
112
```

### pg16-t05-B

Trace SHA-256: `e1dca9d17a39e13dc571f560473453d98898cff0b341adaec6a90d54ec9f590b`

Applied filter: `null`

#### Rank 1: `B:01958df56e561fe2cdc25d461bbb1750c7facb0db7ca93b52fdae932123c2dfa`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [2242,2722).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
The allowed contents of a RETURNING clause are the same as a SELECT command's output list (see
Section 7.3). It can contain column names of the command's target table, or value expressions using
those columns. A common shorthand is RETURNING *, which selects all columns of the target table
in order.
In an INSERT, the data available to RETURNING is the row as it was inserted. This is not so useful in
trivial inserts, since it would just repeat the data provided by the client. 
```

#### Rank 2: `B:2447659b09309fadd14616ad9fb29169988c2b7a5169bd9808a3d70985cffdab`

Physical page 151; printed page 113; section `Data Manipulation`; offsets [437,735).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 151: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO users (firstname, lastname) VALUES ('Joe', 'Cool')
RETURNING id;
The RETURNING clause is also very useful with INSERT ... SELECT.

```

Retrieved chunk (verbatim):

```text
For example:
DELETE FROM products
WHERE obsoletion_date = 'today'
RETURNING *;
If there are triggers (Chapter 39) on the target table, the data available to RETURNING is the row as
modified by the triggers. Thus, inspecting columns computed by triggers is another common use-case
for RETURNING.
113
```

#### Rank 3: `B:f670f4319d3f3a6a55e1c99f9d8faedaf5cc88d650cbe125d8dcb688efa901c0`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [1835,2242).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
Returning Data from Modified Rows
Sometimes it is useful to obtain data from modified rows while they are being manipulated. The
INSERT, UPDATE, and DELETE commands all have an optional RETURNING clause that supports
this. Use of RETURNING avoids performing an extra database query to collect the data, and is
especially valuable when it would otherwise be difficult to identify the modified rows reliably.

```

### pg16-t05-C

Trace SHA-256: `ddeeae65cb691ee5e1375c2ca1c9560fa663854f310f6df200860e20bd9973ef`

Applied filter: `null`

#### Rank 1: `B:01958df56e561fe2cdc25d461bbb1750c7facb0db7ca93b52fdae932123c2dfa`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [2242,2722).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
The allowed contents of a RETURNING clause are the same as a SELECT command's output list (see
Section 7.3). It can contain column names of the command's target table, or value expressions using
those columns. A common shorthand is RETURNING *, which selects all columns of the target table
in order.
In an INSERT, the data available to RETURNING is the row as it was inserted. This is not so useful in
trivial inserts, since it would just repeat the data provided by the client. 
```

#### Rank 2: `B:2447659b09309fadd14616ad9fb29169988c2b7a5169bd9808a3d70985cffdab`

Physical page 151; printed page 113; section `Data Manipulation`; offsets [437,735).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 151: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
INSERT INTO users (firstname, lastname) VALUES ('Joe', 'Cool')
RETURNING id;
The RETURNING clause is also very useful with INSERT ... SELECT.

```

Retrieved chunk (verbatim):

```text
For example:
DELETE FROM products
WHERE obsoletion_date = 'today'
RETURNING *;
If there are triggers (Chapter 39) on the target table, the data available to RETURNING is the row as
modified by the triggers. Thus, inspecting columns computed by triggers is another common use-case
for RETURNING.
113
```

#### Rank 3: `B:f670f4319d3f3a6a55e1c99f9d8faedaf5cc88d650cbe125d8dcb688efa901c0`

Physical page 150; printed page 112; section `Data Manipulation`; offsets [1835,2242).

Source: https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-A4.pdf

Section provenance from manifest: PDF physical page 148: chapter heading; page 150: chapter heading or running header

Source page heading excerpt:

```text
Data Manipulation
UPDATE products SET price = price * 1.10;
As you see, the expression for the new value can refer to the existing value(s) in the row. We also 
```

Retrieved chunk (verbatim):

```text
Returning Data from Modified Rows
Sometimes it is useful to obtain data from modified rows while they are being manipulated. The
INSERT, UPDATE, and DELETE commands all have an optional RETURNING clause that supports
this. Use of RETURNING avoids performing an extra database query to collect the data, and is
especially valuable when it would otherwise be difficult to identify the modified rows reliably.

```
