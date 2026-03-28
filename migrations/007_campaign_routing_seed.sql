-- Migration 007: Seed campaign routing table
-- Idempotent: uses INSERT ... ON CONFLICT DO UPDATE

INSERT INTO dabbahwala.campaign_routing (
    lifecycle_segment,
    campaign_name,
    instantly_campaign_id,
    instantly_campaign_name,
    template_id,
    daily_limit,
    is_active
)
VALUES
    (
        'cold',
        'cold_outreach',
        'CAMPAIGN_COLD_ID',
        'NURTURE_SLOW',
        'template_cold_outreach',
        30,
        TRUE
    ),
    (
        'engaged',
        'engaged_nurture',
        'CAMPAIGN_ENGAGED_ID',
        'PROMO_STANDARD',
        'template_engaged_nurture',
        50,
        TRUE
    ),
    (
        'active_customer',
        'active_retention',
        'CAMPAIGN_ACTIVE_ID',
        'ACTIVE_CUSTOMER',
        'template_active_retention',
        50,
        TRUE
    ),
    (
        'new_customer',
        'new_customer_onboarding',
        'CAMPAIGN_NEW_ID',
        'NEW_CUSTOMER_ONBOARDING',
        'template_new_customer',
        50,
        TRUE
    ),
    (
        'lapsed_customer',
        'lapsed_reactivation',
        'CAMPAIGN_LAPSED_ID',
        'PROMO_AGGRESSIVE',
        'template_lapsed_reactivation',
        40,
        TRUE
    ),
    (
        'reactivation_candidate',
        'win_back',
        'CAMPAIGN_WINBACK_ID',
        'REACTIVATION',
        'template_win_back',
        30,
        TRUE
    ),
    (
        'cooling',
        'cooling_save',
        'CAMPAIGN_COOLING_ID',
        'APP_TO_DIRECT',
        'template_cooling_save',
        10,
        TRUE
    )
ON CONFLICT (lifecycle_segment) DO UPDATE SET
    campaign_name           = EXCLUDED.campaign_name,
    instantly_campaign_id   = EXCLUDED.instantly_campaign_id,
    instantly_campaign_name = EXCLUDED.instantly_campaign_name,
    template_id             = EXCLUDED.template_id,
    daily_limit             = EXCLUDED.daily_limit,
    is_active               = EXCLUDED.is_active,
    updated_at              = NOW();
