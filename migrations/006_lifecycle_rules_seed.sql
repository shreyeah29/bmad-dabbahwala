-- Migration 006: Seed lifecycle segment rules
-- Idempotent: uses INSERT ... ON CONFLICT DO UPDATE

INSERT INTO dabbahwala.rules (rule_name, rule_type, conditions, actions, priority, is_active)
VALUES
    (
        'cold_to_engaged',
        'lifecycle_transition',
        '{"from_segment": "cold", "predicate": "has_event_last_30d AND order_count = 0"}',
        '[{"set_segment": "engaged"}]',
        10,
        TRUE
    ),
    (
        'engaged_to_active_customer',
        'lifecycle_transition',
        '{"from_segment": "engaged", "predicate": "last_order_at >= NOW() - INTERVAL 30 days"}',
        '[{"set_segment": "active_customer"}]',
        20,
        TRUE
    ),
    (
        'cold_to_active_customer',
        'lifecycle_transition',
        '{"from_segment": "cold", "predicate": "last_order_at >= NOW() - INTERVAL 30 days"}',
        '[{"set_segment": "active_customer"}]',
        20,
        TRUE
    ),
    (
        'new_order_sets_new_customer',
        'lifecycle_transition',
        '{"predicate": "order_count = 1 AND first_order_at >= NOW() - INTERVAL 7 days"}',
        '[{"set_segment": "new_customer"}]',
        25,
        TRUE
    ),
    (
        'new_customer_to_active',
        'lifecycle_transition',
        '{"from_segment": "new_customer", "predicate": "order_count >= 2 AND last_order_at >= NOW() - INTERVAL 30 days"}',
        '[{"set_segment": "active_customer"}]',
        30,
        TRUE
    ),
    (
        'active_customer_to_lapsed',
        'lifecycle_transition',
        '{"from_segment": "active_customer", "predicate": "last_order_at < NOW() - INTERVAL 60 days OR last_order_at IS NULL"}',
        '[{"set_segment": "lapsed_customer"}]',
        40,
        TRUE
    ),
    (
        'lapsed_to_reactivation_candidate',
        'lifecycle_transition',
        '{"from_segment": "lapsed_customer", "predicate": "last_order_at < NOW() - INTERVAL 90 days OR last_order_at IS NULL"}',
        '[{"set_segment": "reactivation_candidate"}]',
        50,
        TRUE
    ),
    (
        'cooling_protection',
        'lifecycle_transition',
        '{"predicate": "cooling_until IS NOT NULL AND cooling_until > NOW()"}',
        '[{"set_segment": "cooling", "block_campaigns": true}]',
        5,
        TRUE
    ),
    (
        'optout_protection',
        'lifecycle_transition',
        '{"predicate": "opted_out = TRUE"}',
        '[{"set_segment": "optout", "block_all": true}]',
        1,
        TRUE
    )
ON CONFLICT (rule_name) DO UPDATE SET
    conditions  = EXCLUDED.conditions,
    actions     = EXCLUDED.actions,
    priority    = EXCLUDED.priority,
    is_active   = EXCLUDED.is_active;
