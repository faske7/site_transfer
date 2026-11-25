"""Additive migration; run with previous API and worker stopped."""


def upgrade(conn):
    conn.execute("""
        ALTER TABLE capture_jobs
          ADD COLUMN attempt integer NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),
          ADD COLUMN retry_of uuid REFERENCES capture_jobs(id),
          ADD COLUMN owner_token uuid,
          ADD COLUMN lease_until timestamptz,
          ADD COLUMN heartbeat_at timestamptz,
          ADD COLUMN dispatch_after timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN dispatch_attempts integer NOT NULL DEFAULT 0,
          ADD COLUMN kit_attempt integer NOT NULL DEFAULT 0 CHECK (kit_attempt BETWEEN 0 AND 3)
    """)
    conn.execute("CREATE UNIQUE INDEX capture_retry_once ON capture_jobs(retry_of) WHERE retry_of IS NOT NULL")
    conn.execute("""
        CREATE INDEX capture_dispatch_due ON capture_jobs(dispatch_after)
        WHERE status='queued' OR kit_status='pending'
    """)
    conn.execute("""
        CREATE TABLE lifecycle_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            job_id uuid NOT NULL REFERENCES capture_jobs(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            status text NOT NULL, kit_status text NOT NULL,
            attempt integer NOT NULL, kit_attempt integer NOT NULL,
            dispatch_attempts integer NOT NULL, cancel_requested boolean NOT NULL,
            error text
        )
    """)
    conn.execute("CREATE INDEX lifecycle_events_job ON lifecycle_events(job_id,id DESC)")
    conn.execute("""
        CREATE TABLE worker_heartbeat (
            name text PRIMARY KEY, seen_at timestamptz NOT NULL
        )
    """)
    # A legacy active job has no ownership proof. Keep evidence; do not replay its UUID.
    conn.execute("""
        UPDATE capture_jobs SET status='failed', error='Interrupted by lifecycle upgrade; retry as a new run',
            kit_status=CASE WHEN pipeline_enabled THEN 'failed' ELSE kit_status END,
            updated_at=now() WHERE status IN ('running','queued')
    """)
    conn.execute("""
        UPDATE capture_jobs SET kit_status='failed', kit_info='{"error":"Interrupted by lifecycle upgrade; retry saved capture"}'
        WHERE kit_status='building'
    """)
    conn.execute("""
        UPDATE capture_jobs SET kit_status='failed'
        WHERE kit_status='pending' AND status NOT IN ('completed','partial')
    """)
    conn.execute("""
        CREATE FUNCTION record_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF ROW(OLD.status, OLD.kit_status, OLD.attempt, OLD.kit_attempt,
                       OLD.dispatch_attempts, OLD.cancel_requested, OLD.error)
                    IS NOT DISTINCT FROM
                   ROW(NEW.status, NEW.kit_status, NEW.attempt, NEW.kit_attempt,
                       NEW.dispatch_attempts, NEW.cancel_requested, NEW.error) THEN
                    RETURN NEW;
                END IF;
            END IF;
            INSERT INTO lifecycle_events(job_id,status,kit_status,attempt,kit_attempt,
                                        dispatch_attempts,cancel_requested,error)
            VALUES(NEW.id,NEW.status,NEW.kit_status,NEW.attempt,NEW.kit_attempt,
                   NEW.dispatch_attempts,NEW.cancel_requested,NEW.error);
            RETURN NEW;
        END;
        $$
    """)
    conn.execute("""
        CREATE TRIGGER capture_lifecycle_event AFTER INSERT OR UPDATE ON capture_jobs
        FOR EACH ROW EXECUTE FUNCTION record_lifecycle_event()
    """)
    conn.execute("""
        INSERT INTO lifecycle_events(job_id,status,kit_status,attempt,kit_attempt,dispatch_attempts,cancel_requested,error)
        SELECT id,status,kit_status,attempt,kit_attempt,dispatch_attempts,cancel_requested,error FROM capture_jobs
    """)
