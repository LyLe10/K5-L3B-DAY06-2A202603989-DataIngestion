# Coherence: selected chunks and source context

Human labels are blank in coherence.csv. Score each selected chunk on its own; source context only identifies omissions. C uses the identical B chunk. See NOTICE.txt.

## H01-A

Physical page 97; printed page 59; anchor 1721; chunk `A:2b6d70982f37f1424594ba3bab409311c35d4808f7699c32bd27264192b61bcd` [1350,1850).

Selected chunk (verbatim):

```text
e will see how to deal with this issue.
Each column has a data type. The data type constrains the set of possible values that can be assigned to
a column and assigns semantics to the data stored in the column so that it can be used for computations.
For instance, a column declared to be of a numerical type will not accept arbitrary text strings, and
the data stored in such a column can be used for mathematical computations. By contrast, a column
declared to be of a character string type will acc
```

Source before chunk (up to 180 chars, not part of chunk):

```text
sible to have several completely identical rows in a table. This
is a consequence of the mathematical model that underlies SQL but is usually not desirable. Later in
this chapter w
```

Source after chunk (up to 180 chars, not part of chunk):

```text
ept almost any kind of data but it does not lend itself
to mathematical calculations, although other operations such as string concatenation are available.
PostgreSQL includes a si
```

## H01-B

Physical page 97; printed page 59; anchor 1721; chunk `B:5427dd87d957b5d58ea8844eeb1fa6ababf9d437309dc06b4dbab2310de9ac7d` [1327,1778).

Selected chunk (verbatim):

```text
Later in
this chapter we will see how to deal with this issue.
Each column has a data type. The data type constrains the set of possible values that can be assigned to
a column and assigns semantics to the data stored in the column so that it can be used for computations.
For instance, a column declared to be of a numerical type will not accept arbitrary text strings, and
the data stored in such a column can be used for mathematical computations. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
s to rows, so it is possible to have several completely identical rows in a table. This
is a consequence of the mathematical model that underlies SQL but is usually not desirable. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
By contrast, a column
declared to be of a character string type will accept almost any kind of data but it does not lend itself
to mathematical calculations, although other operati
```

## H02-A

Physical page 98; printed page 60; anchor 1355; chunk `A:a4e799582379a786360f585c4f706b5f4f2b81533ee3da7a71e1820b64db6317` [900,1400).

Selected chunk (verbatim):

```text
ble before creating it, ignoring any error messages, so that the
script works whether or not the table exists. (If you like, you can use the DROP TABLE IF EXISTS
variant to avoid the error messages, but this is not standard SQL.)
If you need to modify a table that already exists, see Section 5.6 later in this chapter.
With the tools discussed so far you can create fully functional tables. The remainder of this chapter is
concerned with adding features to the table definition to ensure data integ
```

Source before chunk (up to 180 chars, not part of chunk):

```text
_first_table;
DROP TABLE products;
Attempting to drop a table that does not exist is an error. Nevertheless, it is common in SQL script files
to unconditionally try to drop each ta
```

Source after chunk (up to 180 chars, not part of chunk):

```text
rity, security, or convenience.
If you are eager to fill your tables with data now you can skip ahead to Chapter 6 and read the rest
of this chapter later.
5.2. Default Values
A co
```

## H02-B

Physical page 98; printed page 60; anchor 1355; chunk `B:6cf338bff5ab46be427c3db9ce01ea86be080ca0ad9e6b60b83c54e4762f8409` [1292,1764).

Selected chunk (verbatim):

```text
The remainder of this chapter is
concerned with adding features to the table definition to ensure data integrity, security, or convenience.
If you are eager to fill your tables with data now you can skip ahead to Chapter 6 and read the rest
of this chapter later.
5.2. Default Values
A column can be assigned a default value. When a new row is created and no values are specified
for some of the columns, those columns will be filled with their respective default values. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
ot standard SQL.)
If you need to modify a table that already exists, see Section 5.6 later in this chapter.
With the tools discussed so far you can create fully functional tables. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
A data
manipulation command can also request explicitly that a column be set to its default value, without
having to know what that value is. (Details about data manipulation comma
```

## H03-A

Physical page 99; printed page 61; anchor 1243; chunk `A:680785feffb3ebee1bcc0d00d86e95c55d73a4f21f203647381dd71a22d2c502` [900,1400).

Selected chunk (verbatim):

```text
erated column is similar to a
materialized view (except that it is always updated automatically). PostgreSQL currently implements
only stored generated columns.
To create a generated column, use the GENERATED ALWAYS AS clause in CREATE TABLE, for
example:
CREATE TABLE people (
...,
height_cm numeric,
height_in numeric GENERATED ALWAYS AS (height_cm / 2.54) STORED
);
The keyword STORED must be specified to choose the stored kind of generated column. See CREATE
TABLE for more details.
A generated 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
s
if it were a normal column. A virtual generated column occupies no storage and is computed when it is
read. Thus, a virtual generated column is similar to a view and a stored gen
```

Source after chunk (up to 180 chars, not part of chunk):

```text
column cannot be written to directly. In INSERT or UPDATE commands, a value cannot
be specified for a generated column, but the keyword DEFAULT may be specified.
Consider the diffe
```

## H03-B

Physical page 99; printed page 61; anchor 1243; chunk `B:e237cf18f610bca3c341f8aa57b1bf756c27ca3c2f4d0598411b56f15c8a9250` [1061,1438).

Selected chunk (verbatim):

```text
To create a generated column, use the GENERATED ALWAYS AS clause in CREATE TABLE, for
example:
CREATE TABLE people (
...,
height_cm numeric,
height_in numeric GENERATED ALWAYS AS (height_cm / 2.54) STORED
);
The keyword STORED must be specified to choose the stored kind of generated column. See CREATE
TABLE for more details.
A generated column cannot be written to directly. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
ew and a stored generated column is similar to a
materialized view (except that it is always updated automatically). PostgreSQL currently implements
only stored generated columns.

```

Source after chunk (up to 180 chars, not part of chunk):

```text
In INSERT or UPDATE commands, a value cannot
be specified for a generated column, but the keyword DEFAULT may be specified.
Consider the differences between a column with a default
```

## H04-A

Physical page 100; printed page 62; anchor 1693; chunk `A:d590313cfc48da2ec46c904159cd8d94dbdfa1f9d7fa4ff166323da0b51da94a` [1350,1850).

Selected chunk (verbatim):

```text
atically be copied from the parent. ALTER TABLE ... ATTACH PARTITION will
insist that parent and child columns already match as to generation status, but it will not require
their generation expressions to match.
• In case of multiple inheritance, if one parent column is a generated column, then all parent
columns must be generated columns. If they do not all have the same generation expression, then
the desired expression for the child must be specified explicitly.
Additional considerations app
```

Source before chunk (up to 180 chars, not part of chunk):

```text
tch.
• Similarly for partitioned tables, if you write a child column definition without any GENERATED
clause in CREATE TABLE ... PARTITION OF , then its GENERATED clause will
autom
```

Source after chunk (up to 180 chars, not part of chunk):

```text
ly to the use of generated columns.
• Generated columns maintain access privileges separately from their underlying base columns. So,
it is possible to arrange it so that a particu
```

## H04-B

Physical page 100; printed page 62; anchor 1693; chunk `B:2861c89f0eac2e24a2be461251d37637c994f5f3c04b85efcdf8c736bb383458` [1402,1886).

Selected chunk (verbatim):

```text
ATTACH PARTITION will
insist that parent and child columns already match as to generation status, but it will not require
their generation expressions to match.
• In case of multiple inheritance, if one parent column is a generated column, then all parent
columns must be generated columns. If they do not all have the same generation expression, then
the desired expression for the child must be specified explicitly.
Additional considerations apply to the use of generated columns.

```

Source before chunk (up to 180 chars, not part of chunk):

```text
e a child column definition without any GENERATED
clause in CREATE TABLE ... PARTITION OF , then its GENERATED clause will
automatically be copied from the parent. ALTER TABLE ... 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
• Generated columns maintain access privileges separately from their underlying base columns. So,
it is possible to arrange it so that a particular role can read from a generated c
```

## H05-A

Physical page 101; printed page 63; anchor 1252; chunk `A:624c1199e68accb41511baeaf7abddfb8bd0ec9b474f5ae23fdb338ce5c0c0a5` [900,1400).

Selected chunk (verbatim):

```text
roducts (
product_no integer,
name text,
price numeric CONSTRAINT positive_price CHECK (price > 0)
);
So, to specify a named constraint, use the key word CONSTRAINT followed by an identifier followed
by the constraint definition. (If you don't specify a constraint name in this way, the system chooses
a name for you.)
A check constraint can also refer to several columns. Say you store a regular price and a discounted
price, and you want to ensure that the discounted price is lower than the regula
```

Source before chunk (up to 180 chars, not part of chunk):

```text

You can also give the constraint a separate name. This clarifies error messages and allows you to refer
to the constraint when you need to change it. The syntax is:
CREATE TABLE p
```

Source after chunk (up to 180 chars, not part of chunk):

```text
r price:
CREATE TABLE products (
product_no integer,
name text,
price numeric CHECK (price > 0),
discounted_price numeric CHECK (discounted_price > 0),
CHECK (price > discounted_pr
```

## H05-B

Physical page 101; printed page 63; anchor 1252; chunk `B:5bd0576c5d375f1144a8b2ba788acee8705346c59de2ae2e27b5e70af37330a8` [871,1273).

Selected chunk (verbatim):

```text
The syntax is:
CREATE TABLE products (
product_no integer,
name text,
price numeric CONSTRAINT positive_price CHECK (price > 0)
);
So, to specify a named constraint, use the key word CONSTRAINT followed by an identifier followed
by the constraint definition. (If you don't specify a constraint name in this way, the system chooses
a name for you.)
A check constraint can also refer to several columns. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
ould not make too much sense.
You can also give the constraint a separate name. This clarifies error messages and allows you to refer
to the constraint when you need to change it. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
Say you store a regular price and a discounted
price, and you want to ensure that the discounted price is lower than the regular price:
CREATE TABLE products (
product_no integer,

```

## H06-A

Physical page 102; printed page 64; anchor 1126; chunk `A:a08f260e97026a6030374c472357810c2301b2d47ddec936ee70f46499fc8265` [900,1400).

Selected chunk (verbatim):

```text
ain null values,
the not-null constraint described in the next section can be used.
Note
PostgreSQL does not support CHECK constraints that reference table data other than the new
or updated row being checked. While a CHECK constraint that violates this rule may appear
to work in simple tests, it cannot guarantee that the database will not reach a state in which
the constraint condition is false (due to subsequent changes of the other row(s) involved). This
would cause a database dump and restor
```

Source before chunk (up to 180 chars, not part of chunk):

```text
. Since most expressions will evaluate to the null value if any operand is null, they will not
prevent null values in the constrained columns. To ensure that a column does not cont
```

Source after chunk (up to 180 chars, not part of chunk):

```text
e to fail. The restore could fail even when the complete
database state is consistent with the constraint, due to rows not being loaded in an order that
will satisfy the constraint
```

## H06-B

Physical page 102; printed page 64; anchor 1126; chunk `B:5b3f300cc4864fada187774e2557a17ab9c3b765b2ecc14734a97e90431e2771` [1110,1582).

Selected chunk (verbatim):

```text
While a CHECK constraint that violates this rule may appear
to work in simple tests, it cannot guarantee that the database will not reach a state in which
the constraint condition is false (due to subsequent changes of the other row(s) involved). This
would cause a database dump and restore to fail. The restore could fail even when the complete
database state is consistent with the constraint, due to rows not being loaded in an order that
will satisfy the constraint. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
constraint described in the next section can be used.
Note
PostgreSQL does not support CHECK constraints that reference table data other than the new
or updated row being checked. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
If possible, use UNIQUE, EXCLUDE, or FOREIGN KEY constraints
to express cross-row and cross-table restrictions.
If what you desire is a one-time check against other rows at row ins
```

## H07-A

Physical page 103; printed page 65; anchor 1204; chunk `A:1c139e8f9b26ae9e0f5a5f98cf3a72b390fd752de60bde7dd8318d1f41a65b7b` [900,1400).

Selected chunk (verbatim):

```text
oducts (
product_no integer NOT NULL,
name text NOT NULL,
price numeric
);
A not-null constraint is always written as a column constraint. A not-null constraint is functionally
equivalent to creating a check constraint CHECK ( column_name IS NOT NULL) , but in
PostgreSQL creating an explicit not-null constraint is more efficient. The drawback is that you cannot
give explicit names to not-null constraints created this way.
Of course, a column can have more than one constraint. Just write the cons
```

Source before chunk (up to 180 chars, not part of chunk):

```text
ecking it against all table
rows.
5.4.2. Not-Null Constraints
A not-null constraint simply specifies that a column must not assume the null value. A syntax example:
CREATE TABLE pr
```

Source after chunk (up to 180 chars, not part of chunk):

```text
traints one after another:
CREATE TABLE products (
product_no integer NOT NULL,
name text NOT NULL,
price numeric NOT NULL CHECK (price > 0)
);
The order doesn't matter. It does no
```

## H07-B

Physical page 103; printed page 65; anchor 1204; chunk `B:f619e42075c0d7b00078f8ff401575e3e173ec99da456a30899beb1450874af0` [867,1326).

Selected chunk (verbatim):

```text
A syntax example:
CREATE TABLE products (
product_no integer NOT NULL,
name text NOT NULL,
price numeric
);
A not-null constraint is always written as a column constraint. A not-null constraint is functionally
equivalent to creating a check constraint CHECK ( column_name IS NOT NULL) , but in
PostgreSQL creating an explicit not-null constraint is more efficient. The drawback is that you cannot
give explicit names to not-null constraints created this way.

```

Source before chunk (up to 180 chars, not part of chunk):

```text
-add the constraint, thereby rechecking it against all table
rows.
5.4.2. Not-Null Constraints
A not-null constraint simply specifies that a column must not assume the null value. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
Of course, a column can have more than one constraint. Just write the constraints one after another:
CREATE TABLE products (
product_no integer NOT NULL,
name text NOT NULL,
price 
```

## H08-A

Physical page 104; printed page 66; anchor 904; chunk `A:643dd5b7da710a46e8c2b253a082ff176739594f2277abeb41fed6b3526bc8df` [450,950).

Selected chunk (verbatim):

```text
ique constraint for a group of columns, write it as a table constraint with the column
names separated by commas:
CREATE TABLE example (
a integer,
b integer,
c integer,
UNIQUE (a, c)
);
This specifies that the combination of values in the indicated columns is unique across the whole table,
though any one of the columns need not be (and ordinarily isn't) unique.
You can assign your own name for a unique constraint, in the usual way:
CREATE TABLE products (
product_no integer CONSTRAINT must_be_d
```

Source before chunk (up to 180 chars, not part of chunk):

```text
written as a column constraint, and:
CREATE TABLE products (
product_no integer,
name text,
price numeric,
UNIQUE (product_no)
);
when written as a table constraint.
To define a un
```

Source after chunk (up to 180 chars, not part of chunk):

```text
ifferent UNIQUE,
name text,
price numeric
);
Adding a unique constraint will automatically create a unique B-tree index on the column or group of
columns listed in the constraint. 
```

## H08-B

Physical page 104; printed page 66; anchor 904; chunk `B:92d5b820d39bc8b159bad1e10b737fd76a3d9a90f880b8c36426bfe9e7b96e6c` [815,1306).

Selected chunk (verbatim):

```text
You can assign your own name for a unique constraint, in the usual way:
CREATE TABLE products (
product_no integer CONSTRAINT must_be_different UNIQUE,
name text,
price numeric
);
Adding a unique constraint will automatically create a unique B-tree index on the column or group of
columns listed in the constraint. A uniqueness restriction covering only some rows cannot be written
as a unique constraint, but it is possible to enforce such a restriction by creating a unique partial index.

```

Source before chunk (up to 180 chars, not part of chunk):

```text
;
This specifies that the combination of values in the indicated columns is unique across the whole table,
though any one of the columns need not be (and ordinarily isn't) unique.

```

Source after chunk (up to 180 chars, not part of chunk):

```text
In general, a unique constraint is violated if there is more than one row in the table where the values of
all of the columns included in the constraint are equal. By default, two 
```

## H09-A

Physical page 105; printed page 67; anchor 931; chunk `A:9caa16044b5a4105e38e86bb4c86eb0f7621d56cecd41ea4f0d79d8b10f99cab` [450,950).

Selected chunk (verbatim):

```text
when developing applications that are
intended to be portable.
5.4.4. Primary Keys
A primary key constraint indicates that a column, or group of columns, can be used as a unique
identifier for rows in the table. This requires that the values be both unique and not null. So, the
following two table definitions accept the same data:
CREATE TABLE products (
product_no integer UNIQUE NOT NULL,
name text,
price numeric
);
CREATE TABLE products (
product_no integer PRIMARY KEY,
name text,
price numeri
```

Source before chunk (up to 180 chars, not part of chunk):

```text
INCT . The default null
treatment in unique constraints is implementation-defined according to the SQL standard, and other
implementations have a different behavior. So be careful 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
c
);
Primary keys can span more than one column; the syntax is similar to unique constraints:
CREATE TABLE example (
a integer,
b integer,
c integer,
PRIMARY KEY (a, c)
);
Adding a
```

## H09-B

Physical page 105; printed page 67; anchor 931; chunk `B:c1ffade09f2e58e6c312ad2b66893ab8aaa2251954b349a6380e6db299c7063a` [721,1217).

Selected chunk (verbatim):

```text
So, the
following two table definitions accept the same data:
CREATE TABLE products (
product_no integer UNIQUE NOT NULL,
name text,
price numeric
);
CREATE TABLE products (
product_no integer PRIMARY KEY,
name text,
price numeric
);
Primary keys can span more than one column; the syntax is similar to unique constraints:
CREATE TABLE example (
a integer,
b integer,
c integer,
PRIMARY KEY (a, c)
);
Adding a primary key will automatically create a unique B-tree index on the column or group of

```

Source before chunk (up to 180 chars, not part of chunk):

```text
y key constraint indicates that a column, or group of columns, can be used as a unique
identifier for rows in the table. This requires that the values be both unique and not null. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
columns listed in the primary key, and will force the column(s) to be marked NOT NULL.
A table can have at most one primary key. (There can be any number of unique and not-null con
```

## H10-A

Physical page 106; printed page 68; anchor 987; chunk `A:bcd6096cc56221937f90eeedb03b8b010af3d3578de2d6685556afe88d4053a9` [900,1400).

Selected chunk (verbatim):

```text
erences the products table:
CREATE TABLE orders (
order_id integer PRIMARY KEY,
product_no integer REFERENCES products (product_no),
quantity integer
);
Now it is impossible to create orders with non-NULL product_no entries that do not appear in
the products table.
We say that in this situation the orders table is the referencing table and the products table is the
referenced table. Similarly, there are referencing and referenced columns.
You can also shorten the above command to:
CREATE TABLE o
```

Source before chunk (up to 180 chars, not part of chunk):

```text
 of those products. We want to ensure that the orders
table only contains orders of products that actually exist. So we define a foreign key constraint in the
orders table that ref
```

Source after chunk (up to 180 chars, not part of chunk):

```text
rders (
order_id integer PRIMARY KEY,
product_no integer REFERENCES products,
quantity integer
);
because in absence of a column list the primary key of the referenced table is use
```

## H10-B

Physical page 106; printed page 68; anchor 987; chunk `B:cce353e962fc4ad207b117999efbfce3aa4f97242edba8c0999a3cc1161b053e` [834,1286).

Selected chunk (verbatim):

```text
So we define a foreign key constraint in the
orders table that references the products table:
CREATE TABLE orders (
order_id integer PRIMARY KEY,
product_no integer REFERENCES products (product_no),
quantity integer
);
Now it is impossible to create orders with non-NULL product_no entries that do not appear in
the products table.
We say that in this situation the orders table is the referencing table and the products table is the
referenced table. 
```

Source before chunk (up to 180 chars, not part of chunk):

```text
price numeric
);
Let's also assume you have a table storing orders of those products. We want to ensure that the orders
table only contains orders of products that actually exist. 
```

Source after chunk (up to 180 chars, not part of chunk):

```text
Similarly, there are referencing and referenced columns.
You can also shorten the above command to:
CREATE TABLE orders (
order_id integer PRIMARY KEY,
product_no integer REFERENCE
```
