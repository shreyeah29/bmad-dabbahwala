-- Migration 001: Base schema, extensions, and enum types
-- Idempotent: safe to run multiple times

CREATE SCHEMA IF NOT EXISTS dabbahwala;

CREATE EXTENSION IF NOT EXISTS vector;

-- ── Enum: lifecycle_segment ───────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.lifecycle_segment AS ENUM (
        'cold',
        'engaged',
        'active_customer',
        'new_customer',
        'lapsed_customer',
        'reactivation_candidate',
        'cooling',
        'optout'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Enum: campaign_name ───────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.campaign_name AS ENUM (
        'cold_outreach',
        'engaged_nurture',
        'active_retention',
        'lapsed_reactivation',
        'win_back',
        'vip_loyalty',
        'cooling_save',
        'new_customer_onboarding'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Enum: event_type ─────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.event_type AS ENUM (
        'order_placed',
        'order_delivered',
        'order_cancelled',
        'sms_sent',
        'sms_received',
        'email_sent',
        'email_opened',
        'email_clicked',
        'call_made',
        'feedback_received'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Enum: delivery_status_type ────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.delivery_status_type AS ENUM (
        'pending',
        'assigned',
        'picked_up',
        'delivered',
        'failed',
        'cancelled'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Enum: opportunity_action ──────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.opportunity_action AS ENUM (
        'send_sms',
        'send_email',
        'make_call',
        'assign_campaign',
        'flag_for_review',
        'no_action'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── Enum: opportunity_status ──────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE dabbahwala.opportunity_status AS ENUM (
        'pending',
        'actioned',
        'dismissed',
        'expired'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
