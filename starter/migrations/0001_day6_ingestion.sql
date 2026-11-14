-- Checkpoint 4.2: REVIEW ONLY. No database connection is made by the planner.
-- Caller must verify manifest checksum, open ONE transaction and SET LOCAL
-- day6_ingestion.migration_checksum to that verified SHA-256 before this body.
-- No extension installation, external-table mutation or destructive rollback.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SELECT pg_catalog.pg_advisory_xact_lock(6753728366513601);

DO $migration$
DECLARE
    expected_checksum text := current_setting('day6_ingestion.migration_checksum', true);
    applied_checksum text;
    applied_catalog text;
BEGIN
    IF expected_checksum IS NULL OR expected_checksum !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Verified migration checksum was not supplied';
    END IF;
    IF current_database() <> 'day6_lab' OR current_setting('server_encoding') <> 'UTF8'
       OR current_setting('server_version_num')::integer / 10000 <> 16 THEN
        RAISE EXCEPTION 'Expected UTF8 day6_lab on PostgreSQL 16';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_extension e
        JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'vector' AND e.extversion = '0.8.7' AND n.nspname = 'public'
    ) THEN
        RAISE EXCEPTION 'Expected existing public.vector extension 0.8.7';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'day6_ingestion') THEN
        IF to_regclass('day6_ingestion.schema_migrations') IS NULL
           OR to_regprocedure('day6_ingestion.catalog_fingerprint()') IS NULL THEN
            RAISE EXCEPTION 'Unrecognized existing schema; manual review required';
        END IF;
        EXECUTE 'SELECT checksum, catalog_sha256 FROM day6_ingestion.schema_migrations WHERE version = 1 AND name = ''0001_day6_ingestion.sql'''
            INTO applied_checksum, applied_catalog;
        IF applied_checksum IS DISTINCT FROM expected_checksum
           OR (SELECT count(*) FROM day6_ingestion.schema_migrations) <> 1 THEN
            RAISE EXCEPTION 'Unknown migration history or checksum mismatch';
        END IF;
        IF day6_ingestion.catalog_fingerprint() IS DISTINCT FROM applied_catalog THEN
            RAISE EXCEPTION 'Schema catalog drift; manual review required';
        END IF;
        RETURN; -- Recognized, unchanged replay: no DDL/DML.
    END IF;

    CREATE SCHEMA day6_ingestion;

    CREATE TABLE day6_ingestion.schema_migrations (
        version integer PRIMARY KEY CHECK (version > 0),
        name text NOT NULL UNIQUE,
        checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
        catalog_sha256 text NOT NULL CHECK (catalog_sha256 ~ '^[0-9a-f]{64}$'),
        applied_at timestamptz NOT NULL DEFAULT transaction_timestamp()
    );

    CREATE TABLE day6_ingestion.embedding_profiles (
        profile_id text PRIMARY KEY CHECK (profile_id ~ '^[0-9a-f]{64}$'),
        model_name text NOT NULL CHECK (btrim(model_name) <> ''),
        revision text NOT NULL CHECK (revision ~ '^[0-9a-f]{40}$'),
        dimensions integer NOT NULL CHECK (dimensions = 384),
        config_canonical text NOT NULL,
        config jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
        CONSTRAINT profile_content_address CHECK (
            profile_id = encode(sha256(convert_to(config_canonical, 'UTF8')), 'hex')),
        CONSTRAINT profile_config_consistency CHECK ((
            jsonb_typeof(config) = 'object' AND config_canonical::jsonb = config
            AND config ?& ARRAY['profile_schema_version','model_name','revision','dimensions',
                'dtype','pooling','normalize_embeddings','document_prefix','query_prefix',
                'tokenizer','max_seq_length','artifact_sha256','library_versions',
                'device','backend','trust_remote_code','pooling_include_prompt']
            AND config->'profile_schema_version' = '1'::jsonb
            AND config->>'model_name' = model_name AND config->>'revision' = revision
            AND config->'dimensions' = '384'::jsonb
            AND config->>'dtype' = 'float32' AND config->>'pooling' = 'mean'
            AND config->'normalize_embeddings' = 'true'::jsonb
            AND config->>'device' = 'cpu' AND config->>'backend' = 'torch'
            AND config->'trust_remote_code' = 'false'::jsonb
            AND config->'pooling_include_prompt' = 'true'::jsonb
            AND config->>'document_prefix' = 'passage: ' AND config->>'query_prefix' = 'query: '
            AND config->'max_seq_length' = '512'::jsonb
            AND jsonb_typeof(config->'artifact_sha256') = 'object'
            AND config->'artifact_sha256' <> '{}'::jsonb
            AND jsonb_typeof(config->'library_versions') = 'object'
            AND config->'library_versions' <> '{}'::jsonb
            AND jsonb_typeof(config->'tokenizer') = 'object'
            AND config->'tokenizer'->>'name' = model_name
            AND config->'tokenizer'->>'revision' = revision
            AND config->'tokenizer'->'model_max_length' = '512'::jsonb
            AND config->'tokenizer'->'use_fast' = 'true'::jsonb
        ) IS TRUE)
    );

    CREATE TABLE day6_ingestion.strategy_snapshots (
        dataset_id text NOT NULL CHECK (dataset_id ~ '^[a-z0-9][a-z0-9_.-]{0,127}$'),
        profile_id text NOT NULL REFERENCES day6_ingestion.embedding_profiles(profile_id) ON DELETE RESTRICT,
        strategy text NOT NULL CHECK (strategy IN ('A', 'B')),
        snapshot_id text NOT NULL CHECK (snapshot_id ~ '^[0-9a-f]{64}$'),
        manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
        corpus_sha256 text NOT NULL CHECK (corpus_sha256 ~ '^[0-9a-f]{64}$'),
        chunkset_sha256 text NOT NULL CHECK (chunkset_sha256 ~ '^[0-9a-f]{64}$'),
        chunking_config jsonb NOT NULL,
        selected_page_count integer NOT NULL CHECK (selected_page_count >= 30),
        expected_count integer NOT NULL CHECK (expected_count >= selected_page_count),
        actual_count integer NOT NULL CHECK (actual_count >= 0 AND actual_count <= expected_count),
        status text NOT NULL CHECK (status IN ('syncing', 'complete')),
        completed_at timestamptz,
        PRIMARY KEY (dataset_id, profile_id, strategy),
        UNIQUE (dataset_id, profile_id, strategy, snapshot_id, manifest_sha256, corpus_sha256),
        CONSTRAINT snapshot_completion CHECK (
            (status = 'syncing' AND completed_at IS NULL) OR
            (status = 'complete' AND completed_at IS NOT NULL AND actual_count = expected_count)),
        CONSTRAINT baseline_chunking_config CHECK (chunking_config = CASE strategy
            WHEN 'A' THEN '{"strategy":"A","algorithm_version":1,"unit":"characters","parameters":{"size":500,"overlap":50}}'::jsonb
            ELSE '{"strategy":"B","algorithm_version":1,"unit":"characters","parameters":{"max_size":500}}'::jsonb END)
    );

    CREATE TABLE day6_ingestion.chunks (
        dataset_id text NOT NULL,
        profile_id text NOT NULL,
        strategy text NOT NULL CHECK (strategy IN ('A', 'B')),
        chunk_id text NOT NULL CHECK (chunk_id ~ '^[AB]:[0-9a-f]{64}$' AND left(chunk_id, 1) = strategy),
        snapshot_id text NOT NULL,
        manifest_sha256 text NOT NULL,
        corpus_sha256 text NOT NULL,
        document_id text NOT NULL CHECK (btrim(document_id) <> ''),
        source text NOT NULL CHECK (btrim(source) <> ''),
        source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
        physical_page integer NOT NULL CHECK (physical_page > 0),
        printed_page_label text,
        page_id text NOT NULL CHECK (btrim(page_id) <> ''),
        section text NOT NULL CHECK (btrim(section) <> ''),
        text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 500),
        text_sha256 text NOT NULL CHECK (text_sha256 = encode(sha256(convert_to(text, 'UTF8')), 'hex')),
        page_text_sha256 text NOT NULL CHECK (page_text_sha256 ~ '^[0-9a-f]{64}$'),
        normalized_char_count integer NOT NULL CHECK (normalized_char_count > 0),
        start_char integer NOT NULL CHECK (start_char >= 0),
        end_char integer NOT NULL,
        metadata jsonb NOT NULL,
        embedding public.vector(384) NOT NULL,
        PRIMARY KEY (dataset_id, profile_id, strategy, chunk_id),
        FOREIGN KEY (dataset_id, profile_id, strategy, snapshot_id, manifest_sha256, corpus_sha256)
            REFERENCES day6_ingestion.strategy_snapshots
                (dataset_id, profile_id, strategy, snapshot_id, manifest_sha256, corpus_sha256)
            ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
        CONSTRAINT chunk_offsets CHECK (
            end_char > start_char AND end_char <= normalized_char_count
            AND end_char - start_char = char_length(text)),
        CONSTRAINT unit_embedding CHECK (abs(public.vector_norm(embedding) - 1.0) <= 0.00001),
        CONSTRAINT chunk_metadata CHECK ((
            jsonb_typeof(metadata) = 'object'
            AND metadata ?& ARRAY['source_id','page_id','physical_page','printed_page_label',
                'section','section_evidence','version','normalized_char_count','text_sha256',
                'extraction_status','_chunking']
            AND jsonb_typeof(metadata->'source_id') = 'string'
            AND jsonb_typeof(metadata->'page_id') = 'string'
            AND jsonb_typeof(metadata->'section') = 'string'
            AND jsonb_typeof(metadata->'text_sha256') = 'string'
            AND jsonb_typeof(metadata->'version') IN ('string', 'null')
            AND metadata->>'source_id' = document_id AND metadata->>'page_id' = page_id
            AND metadata->>'section' = section
            AND jsonb_typeof(metadata->'section_evidence') = 'string'
            AND btrim(metadata->>'section_evidence') <> ''
            AND metadata->>'extraction_status' = 'ok'
            AND metadata->>'text_sha256' = page_text_sha256
            AND jsonb_typeof(metadata->'physical_page') = 'number'
            AND (metadata->>'physical_page')::integer = physical_page
            AND jsonb_typeof(metadata->'normalized_char_count') = 'number'
            AND (metadata->>'normalized_char_count')::integer = normalized_char_count
            AND metadata->'printed_page_label' = coalesce(to_jsonb(printed_page_label), 'null'::jsonb)
            AND jsonb_typeof(metadata->'_chunking') = 'object'
            AND metadata->'_chunking'->>'strategy' = strategy
            AND jsonb_typeof(metadata->'_chunking'->'start_char') = 'number'
            AND jsonb_typeof(metadata->'_chunking'->'end_char') = 'number'
            AND (metadata->'_chunking'->>'start_char')::integer = start_char
            AND (metadata->'_chunking'->>'end_char')::integer = end_char
        ) IS TRUE)
    );
    CREATE INDEX chunks_section_idx ON day6_ingestion.chunks
        (dataset_id, profile_id, strategy, section);
    CREATE INDEX chunks_page_idx ON day6_ingestion.chunks
        (dataset_id, profile_id, strategy, document_id, physical_page);

    CREATE FUNCTION day6_ingestion.reject_mutation() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
    BEGIN
        RAISE EXCEPTION 'Immutable history/profile or unsupported TRUNCATE on %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END;
    $function$;
    CREATE TRIGGER profiles_immutable BEFORE UPDATE OR DELETE ON day6_ingestion.embedding_profiles
        FOR EACH ROW EXECUTE FUNCTION day6_ingestion.reject_mutation();
    CREATE TRIGGER migrations_immutable BEFORE UPDATE OR DELETE ON day6_ingestion.schema_migrations
        FOR EACH ROW EXECUTE FUNCTION day6_ingestion.reject_mutation();
    CREATE TRIGGER profiles_no_truncate BEFORE TRUNCATE ON day6_ingestion.embedding_profiles
        FOR EACH STATEMENT EXECUTE FUNCTION day6_ingestion.reject_mutation();
    CREATE TRIGGER migrations_no_truncate BEFORE TRUNCATE ON day6_ingestion.schema_migrations
        FOR EACH STATEMENT EXECUTE FUNCTION day6_ingestion.reject_mutation();
    CREATE TRIGGER snapshots_no_truncate BEFORE TRUNCATE ON day6_ingestion.strategy_snapshots
        FOR EACH STATEMENT EXECUTE FUNCTION day6_ingestion.reject_mutation();
    CREATE TRIGGER chunks_no_truncate BEFORE TRUNCATE ON day6_ingestion.chunks
        FOR EACH STATEMENT EXECUTE FUNCTION day6_ingestion.reject_mutation();

    CREATE FUNCTION day6_ingestion.namespace_lock_key(d text, p text, s text) RETURNS bigint
    LANGUAGE sql IMMUTABLE STRICT SET search_path = pg_catalog AS $function$
        SELECT ('x' || substr(encode(sha256(convert_to(
            'day6_ingestion:sync:' || d || ':' || p || ':' || s, 'UTF8')), 'hex'), 1, 16))::bit(64)::bigint
    $function$;
    CREATE FUNCTION day6_ingestion.guard_namespace() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
    BEGIN
        IF TG_OP = 'UPDATE' AND (NEW.dataset_id, NEW.profile_id, NEW.strategy)
            IS DISTINCT FROM (OLD.dataset_id, OLD.profile_id, OLD.strategy) THEN
            RAISE EXCEPTION 'Namespace identity cannot be changed';
        END IF;
        IF TG_TABLE_NAME = 'chunks' THEN
            IF TG_OP = 'UPDATE' AND NEW.chunk_id <> OLD.chunk_id THEN
                RAISE EXCEPTION 'Chunk identity cannot be changed';
            END IF;
        END IF;
        IF TG_TABLE_NAME = 'strategy_snapshots' AND TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Snapshot deletion is not supported in v1';
        END IF;
        IF TG_OP = 'DELETE' THEN
            PERFORM pg_advisory_xact_lock(day6_ingestion.namespace_lock_key(OLD.dataset_id, OLD.profile_id, OLD.strategy));
            RETURN OLD;
        END IF;
        PERFORM pg_advisory_xact_lock(day6_ingestion.namespace_lock_key(NEW.dataset_id, NEW.profile_id, NEW.strategy));
        RETURN NEW;
    END;
    $function$;
    CREATE TRIGGER snapshots_namespace BEFORE INSERT OR UPDATE OR DELETE ON day6_ingestion.strategy_snapshots
        FOR EACH ROW EXECUTE FUNCTION day6_ingestion.guard_namespace();
    CREATE TRIGGER chunks_namespace BEFORE INSERT OR UPDATE OR DELETE ON day6_ingestion.chunks
        FOR EACH ROW EXECUTE FUNCTION day6_ingestion.guard_namespace();

    CREATE FUNCTION day6_ingestion.assert_snapshot_complete() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
    DECLARE
        d text; p text; s text; ledger day6_ingestion.strategy_snapshots%ROWTYPE;
        row_count bigint; page_count bigint; bad_config bigint;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            d := OLD.dataset_id; p := OLD.profile_id; s := OLD.strategy;
        ELSE
            d := NEW.dataset_id; p := NEW.profile_id; s := NEW.strategy;
        END IF;
        SELECT * INTO ledger FROM day6_ingestion.strategy_snapshots
            WHERE dataset_id = d AND profile_id = p AND strategy = s;
        IF NOT FOUND OR ledger.status <> 'complete' THEN
            RAISE EXCEPTION 'Snapshot must be complete at transaction boundary';
        END IF;
        SELECT count(*), count(DISTINCT (document_id, physical_page)),
            count(*) FILTER (WHERE ((metadata->'_chunking') - ARRAY['start_char','end_char','split_sql_statement'])
                IS DISTINCT FROM ledger.chunking_config)
            INTO row_count, page_count, bad_config FROM day6_ingestion.chunks
            WHERE dataset_id = d AND profile_id = p AND strategy = s;
        IF row_count <> ledger.expected_count OR row_count <> ledger.actual_count
            OR page_count <> ledger.selected_page_count OR bad_config <> 0 THEN
            RAISE EXCEPTION 'Snapshot count/pages/chunking config mismatch';
        END IF;
        RETURN NULL;
    END;
    $function$;
    CREATE CONSTRAINT TRIGGER snapshots_complete AFTER INSERT OR UPDATE ON day6_ingestion.strategy_snapshots
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION day6_ingestion.assert_snapshot_complete();
    CREATE CONSTRAINT TRIGGER chunks_complete AFTER INSERT OR UPDATE OR DELETE ON day6_ingestion.chunks
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION day6_ingestion.assert_snapshot_complete();

    CREATE VIEW day6_ingestion.compatible_snapshots AS
        SELECT a.dataset_id, a.profile_id, a.manifest_sha256, a.corpus_sha256,
               a.snapshot_id AS a_snapshot_id, b.snapshot_id AS b_snapshot_id,
               a.actual_count AS a_count, b.actual_count AS b_count
        FROM day6_ingestion.strategy_snapshots a
        JOIN day6_ingestion.strategy_snapshots b
          ON a.dataset_id = b.dataset_id AND a.profile_id = b.profile_id
         AND a.manifest_sha256 = b.manifest_sha256 AND a.corpus_sha256 = b.corpus_sha256
         AND a.selected_page_count = b.selected_page_count
        WHERE a.strategy = 'A' AND b.strategy = 'B'
          AND a.status = 'complete' AND b.status = 'complete';

    CREATE FUNCTION day6_ingestion.catalog_fingerprint() RETURNS text
    LANGUAGE sql STABLE SET search_path = pg_catalog AS $function$
        SELECT encode(sha256(convert_to(coalesce(string_agg(item, E'\n' ORDER BY item), ''), 'UTF8')), 'hex')
        FROM (
            SELECT 'column:' || c.relname || ':' || a.attnum || ':' || a.attname || ':' ||
                format_type(a.atttypid, a.atttypmod) || ':' || a.attnotnull || ':' ||
                coalesce(pg_get_expr(ad.adbin, ad.adrelid), '') AS item
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
            WHERE n.nspname = 'day6_ingestion' AND c.relkind IN ('r', 'v')
            UNION ALL
            SELECT 'constraint:' || c.relname || ':' || x.conname || ':' || pg_get_constraintdef(x.oid, true)
            FROM pg_constraint x JOIN pg_class c ON c.oid = x.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'day6_ingestion'
            UNION ALL
            SELECT 'index:' || indexname || ':' || indexdef FROM pg_indexes WHERE schemaname = 'day6_ingestion'
            UNION ALL
            SELECT 'function:' || pg_get_functiondef(p.oid) FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'day6_ingestion'
            UNION ALL
            SELECT 'trigger:' || pg_get_triggerdef(t.oid, true) || ':' || t.tgenabled::text
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'day6_ingestion' AND NOT t.tgisinternal
            UNION ALL
            SELECT 'view:' || viewname || ':' || definition FROM pg_views WHERE schemaname = 'day6_ingestion'
        ) objects
    $function$;

    INSERT INTO day6_ingestion.schema_migrations (version, name, checksum, catalog_sha256)
        VALUES (1, '0001_day6_ingestion.sql', expected_checksum, day6_ingestion.catalog_fingerprint());
END;
$migration$;
