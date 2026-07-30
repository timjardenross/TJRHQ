"""Strategic Planning Command (MSN-SPC-001).

A thin strategic layer above missions: the six standing domains, an objective
registry, mission alignment, and the compose helpers that surface strategy into
the existing Daily Operating Picture. Pure where possible; Supabase access is
graceful (returns empty/None when unavailable).
"""
