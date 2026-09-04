# GOD — Architectural Decisions

## Decision: Fix analyzer math regex false positive

Date: 2026-09-04
Problem: `brain.analyze()` TYPE_RULES has math regex `\b(calcul|quanto [eé]|soma|multipl|dividi)` where `\bmultipl` matches Portuguese words like "multiplas" (multiple), "multiplicação" (multiplication) as a prefix. Since math rules are checked BEFORE coding rules, coding requests containing these words are misclassified as math, causing the calculator tool to receive non-arithmetic text.

Options:
1. Change "multipl" to "multiplica" in the math regex
2. Add trailing `\b` to the entire math group
3. Reorder TYPE_RULES so coding comes before math
4. Use negative lookahead after "multipl"

Chosen Option: 1 — Change "multipl" to "multiplica"

Reason:
- Option 2 breaks "calcula" (which needs prefix matching)
- Option 3 could cause other regressions (math should generally have priority over coding)
- Option 4 is overly complex for this case
- Option 1 is minimal, targeted, and catches the intended words (multiplica, multiplicação, multiplicar) without matching "multiplas"

Trade-offs:
- If someone writes "multipl" as shorthand for "multiplica", it won't match. Acceptable — "calcula" is the common Portuguese form.
- The regex still allows prefix matching for "calcul" (calcula, calculadora) which is correct.

Rollback: Revert "multiplica" back to "multipl" in brain.py TYPE_RULES.
