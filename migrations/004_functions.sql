-- Migration 004: Stored functions
-- Idempotent: all use CREATE OR REPLACE FUNCTION

SET search_path = dabbahwala;

-- ── ingest_event() ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.ingest_event(
    p_contact_id    INTEGER,
    p_event_type    TEXT,
    p_metadata      JSONB DEFAULT '{}'
) RETURNS INTEGER AS $$
DECLARE
    v_event_id  INTEGER;
BEGIN
    INSERT INTO dabbahwala.events (contact_id, event_type, metadata)
    VALUES (p_contact_id, p_event_type::dabbahwala.event_type, p_metadata)
    RETURNING id INTO v_event_id;

    -- Update contact timestamps on order events
    IF p_event_type = 'order_placed' THEN
        UPDATE dabbahwala.contacts
        SET order_count = order_count + 1,
            last_order_at = NOW(),
            first_order_at = COALESCE(first_order_at, NOW()),
            updated_at = NOW()
        WHERE id = p_contact_id;
    END IF;

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;


-- ── refresh_engagement_rollups() ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.refresh_engagement_rollups(
    p_contact_id INTEGER DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO dabbahwala.engagement_rollups (
        contact_id, orders_7d, orders_30d, spend_7d, spend_30d,
        sms_sent_7d, sms_recv_7d, email_opens_7d, computed_at
    )
    SELECT
        c.id,
        COUNT(DISTINCT o.id) FILTER (WHERE o.created_at >= NOW() - INTERVAL '7 days'),
        COUNT(DISTINCT o.id) FILTER (WHERE o.created_at >= NOW() - INTERVAL '30 days'),
        COALESCE(SUM(o.total_amount) FILTER (WHERE o.created_at >= NOW() - INTERVAL '7 days'), 0),
        COALESCE(SUM(o.total_amount) FILTER (WHERE o.created_at >= NOW() - INTERVAL '30 days'), 0),
        COUNT(e.id) FILTER (WHERE e.event_type = 'sms_sent'     AND e.created_at >= NOW() - INTERVAL '7 days'),
        COUNT(e.id) FILTER (WHERE e.event_type = 'sms_received' AND e.created_at >= NOW() - INTERVAL '7 days'),
        COUNT(e.id) FILTER (WHERE e.event_type = 'email_opened' AND e.created_at >= NOW() - INTERVAL '7 days'),
        NOW()
    FROM dabbahwala.contacts c
    LEFT JOIN dabbahwala.orders o ON o.contact_id = c.id
    LEFT JOIN dabbahwala.events e ON e.contact_id = c.id
    WHERE (p_contact_id IS NULL OR c.id = p_contact_id)
    GROUP BY c.id
    ON CONFLICT (contact_id) DO UPDATE SET
        orders_7d       = EXCLUDED.orders_7d,
        orders_30d      = EXCLUDED.orders_30d,
        spend_7d        = EXCLUDED.spend_7d,
        spend_30d       = EXCLUDED.spend_30d,
        sms_sent_7d     = EXCLUDED.sms_sent_7d,
        sms_recv_7d     = EXCLUDED.sms_recv_7d,
        email_opens_7d  = EXCLUDED.email_opens_7d,
        computed_at     = EXCLUDED.computed_at;
END;
$$ LANGUAGE plpgsql;


-- ── get_contact_detail() ──────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.get_contact_detail(
    p_contact_id INTEGER
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'contact',      row_to_json(c),
        'rollup',       row_to_json(er),
        'recent_orders', (
            SELECT jsonb_agg(row_to_json(o) ORDER BY o.created_at DESC)
            FROM dabbahwala.orders o
            WHERE o.contact_id = c.id
            LIMIT 10
        ),
        'recent_events', (
            SELECT jsonb_agg(row_to_json(e) ORDER BY e.created_at DESC)
            FROM dabbahwala.events e
            WHERE e.contact_id = c.id
            LIMIT 20
        )
    )
    INTO v_result
    FROM dabbahwala.contacts c
    LEFT JOIN dabbahwala.engagement_rollups er ON er.contact_id = c.id
    WHERE c.id = p_contact_id;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;


-- ── get_communication_history() ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.get_communication_history(
    p_contact_id    INTEGER,
    p_limit         INTEGER DEFAULT 50
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'sms', (
            SELECT jsonb_agg(row_to_json(m) ORDER BY m.created_at DESC)
            FROM dabbahwala.telnyx_messages m
            WHERE m.contact_id = p_contact_id
            LIMIT p_limit
        ),
        'calls', (
            SELECT jsonb_agg(row_to_json(c) ORDER BY c.created_at DESC)
            FROM dabbahwala.telnyx_calls c
            WHERE c.contact_id = p_contact_id
            LIMIT p_limit
        )
    ) INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;


-- ── suggest_reactivation_targets() ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.suggest_reactivation_targets(
    p_days_inactive INTEGER DEFAULT 30,
    p_limit         INTEGER DEFAULT 100
) RETURNS TABLE(contact_id INTEGER, email TEXT, last_order_at TIMESTAMPTZ, order_count INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT c.id, c.email, c.last_order_at, c.order_count
    FROM dabbahwala.contacts c
    WHERE c.lifecycle_segment IN ('lapsed_customer', 'reactivation_candidate', 'cooling')
      AND (c.last_order_at IS NULL OR c.last_order_at < NOW() - (p_days_inactive || ' days')::INTERVAL)
      AND c.opted_out = FALSE
    ORDER BY c.order_count DESC, c.last_order_at DESC NULLS LAST
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;


-- ── get_lifecycle_summary() ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.get_lifecycle_summary() RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_object_agg(lifecycle_segment, cnt)
    INTO v_result
    FROM (
        SELECT lifecycle_segment::TEXT, COUNT(*) AS cnt
        FROM dabbahwala.contacts
        WHERE opted_out = FALSE
        GROUP BY lifecycle_segment
    ) t;

    RETURN COALESCE(v_result, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql;


-- ── get_campaign_performance() ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.get_campaign_performance(
    p_days INTEGER DEFAULT 30
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_agg(row_to_json(t))
    INTO v_result
    FROM (
        SELECT
            campaign_name::TEXT,
            lifecycle_segment::TEXT,
            COUNT(*) AS total_pushed,
            COUNT(*) FILTER (WHERE status = 'success') AS successful,
            MIN(pushed_at) AS first_push,
            MAX(pushed_at) AS last_push
        FROM dabbahwala.campaign_push_log
        WHERE pushed_at >= NOW() - (p_days || ' days')::INTERVAL
        GROUP BY campaign_name, lifecycle_segment
        ORDER BY total_pushed DESC
    ) t;

    RETURN COALESCE(v_result, '[]'::JSONB);
END;
$$ LANGUAGE plpgsql;


-- ── generate_daily_report() ───────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.generate_daily_report(
    p_date DATE DEFAULT CURRENT_DATE
) RETURNS JSONB AS $$
DECLARE
    v_result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'date',             p_date,
        'new_contacts',     (SELECT COUNT(*) FROM dabbahwala.contacts WHERE DATE(created_at) = p_date),
        'orders',           (SELECT COUNT(*) FROM dabbahwala.orders WHERE DATE(created_at) = p_date),
        'revenue',          (SELECT COALESCE(SUM(total_amount), 0) FROM dabbahwala.orders WHERE DATE(created_at) = p_date),
        'sms_sent',         (SELECT COUNT(*) FROM dabbahwala.events WHERE event_type = 'sms_sent' AND DATE(created_at) = p_date),
        'lifecycle_summary', dabbahwala.get_lifecycle_summary()
    ) INTO v_result;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;


-- ── create_opportunity() ──────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.create_opportunity(
    p_contact_id        INTEGER,
    p_signal_type       TEXT,
    p_confidence        NUMERIC DEFAULT 0.5,
    p_recommended_action TEXT DEFAULT 'no_action',
    p_notes             TEXT DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
BEGIN
    -- Deduplicate: skip if pending opportunity already exists for same contact+signal
    IF EXISTS (
        SELECT 1 FROM dabbahwala.opportunities
        WHERE contact_id = p_contact_id
          AND signal_type = p_signal_type
          AND status = 'pending'
    ) THEN
        RETURN NULL;
    END IF;

    INSERT INTO dabbahwala.opportunities (contact_id, signal_type, confidence, recommended_action, notes)
    VALUES (
        p_contact_id,
        p_signal_type,
        p_confidence,
        p_recommended_action::dabbahwala.opportunity_action,
        p_notes
    )
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;


-- ── run_lifecycle_cycle() ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION dabbahwala.run_lifecycle_cycle() RETURNS JSONB AS $$
DECLARE
    v_updated   INTEGER := 0;
    v_result    JSONB;
BEGIN
    -- cold → engaged: has at least 1 event in last 30 days but no orders
    UPDATE dabbahwala.contacts SET lifecycle_segment = 'engaged', updated_at = NOW()
    WHERE lifecycle_segment = 'cold'
      AND opted_out = FALSE
      AND id IN (
          SELECT DISTINCT contact_id FROM dabbahwala.events
          WHERE created_at >= NOW() - INTERVAL '30 days'
      )
      AND order_count = 0;
    GET DIAGNOSTICS v_updated = ROW_COUNT;

    -- engaged/cold → active_customer: placed order in last 30 days
    UPDATE dabbahwala.contacts SET lifecycle_segment = 'active_customer', updated_at = NOW()
    WHERE lifecycle_segment IN ('cold', 'engaged')
      AND opted_out = FALSE
      AND last_order_at >= NOW() - INTERVAL '30 days';

    -- active_customer → lapsed_customer: no order in 60 days
    UPDATE dabbahwala.contacts SET lifecycle_segment = 'lapsed_customer', updated_at = NOW()
    WHERE lifecycle_segment = 'active_customer'
      AND opted_out = FALSE
      AND (last_order_at IS NULL OR last_order_at < NOW() - INTERVAL '60 days');

    -- lapsed_customer → reactivation_candidate: no order in 90 days
    UPDATE dabbahwala.contacts SET lifecycle_segment = 'reactivation_candidate', updated_at = NOW()
    WHERE lifecycle_segment = 'lapsed_customer'
      AND opted_out = FALSE
      AND (last_order_at IS NULL OR last_order_at < NOW() - INTERVAL '90 days');

    v_result := jsonb_build_object(
        'cycle_ran_at', NOW(),
        'updated', v_updated
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;
