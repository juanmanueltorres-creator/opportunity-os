# Semantic CAREER Matching — Implementation Plan

1. Add regression tests for domain compatibility, role-family matching, transferable evidence, unrelated-role rejection, and a Bord-like end-to-end ranking case.
2. Confirm RED against current CAREER scoring.
3. Implement CAREER-only domain compatibility without changing the frozen v0.1 scorer.
4. Add deterministic role-family fallback after normal skill/taxonomy resolution for conceptual requirements only.
5. Add CAREER evidence coverage that accepts verified role-backed project/experience evidence only in a matched opportunity domain.
6. Surface matched preferred role-shaped requirements as strengths without making preferred misses mandatory gaps.
7. Verify targeted regression tests, existing Radar/matching tests, compile/diff checks, and full GitHub Actions.
8. Re-run the exact real Bord payload and require `MEDIUM/HIGH + selected_intent=CAREER` while retaining the duration gap/risk.
