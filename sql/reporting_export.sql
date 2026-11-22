-- Exact contact counts preserve the approved frequency view's eligibility and denominator.
SELECT jsonb_build_object(
    'frequency', coalesce(jsonb_agg(to_jsonb(f) - 'source_sha256' ORDER BY campaign), '[]'::jsonb)
) AS p003_export_frequency
FROM p003_bank_campaign.campaign_frequency f
WHERE source_sha256 = '74adfc578bf77a7ff4bb1ba4a9f8709d9e3c6907342959c2c8416847e0afb4d8';
