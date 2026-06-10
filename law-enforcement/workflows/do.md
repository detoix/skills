<purpose>
Analyze freeform user text and route it to the correct mode. This dispatcher never does the work itself.
</purpose>

<process>

<step name="route">
Apply the first matching rule to the latest user message.

| If the latest user message describes... | Route | Result |
|---|---|---|
| Latest user message contains exact phrase `implement` or `do it` | implementation | Proceed with the requested implementation |
| A question: `?`, "do you think", "can we", "could we", "should we", "is it possible", "would it be better", "how would", "what if" | answer-only | Answer only; no edits |
| Review, analyze, investigate, inspect, audit, explain, compare, diagnose | analysis-only | Analyze only; no edits |
| Plan, propose, design, approach, roadmap, strategy, recommendation | plan-only | Produce plan/recommendation only; no edits |
| Direct but ambiguous task wording | clarify | Ask the user to choose a route |

</step>

<step name="dispatch">
If route is `implementation`:

1. Proceed with the requested implementation.

If route is `answer-only`, `analysis-only`, or `plan-only`:

1. Do not edit files.
2. Do not call file-writing tools.
3. Answer, analyze, or plan in text.

If route is `clarify`:

1. Do not edit files.
2. Do not call file-writing tools.
3. Ask a concise route question with the most likely options.

</step>

<step name="deviation_rules">
Apply during any route that inspects, analyzes, or edits code:

- Structural issue or bad pattern: STOP before patching, diagnose, present decision to user, await approval.
- Server lifecycle command: STOP before running, state that user runs the app/server, await user-provided results if needed.
- Removal/replacement residue: STOP before preserving removed behavior as comments, aliases, compatibility shims, fallback branches, dead code, docs, or tests. Produce a clean removal/replacement, or present the compatibility decision to user and await approval.
- Unsure: STOP and ask.

Priority: STOP gates > implementation route > clarify.
</step>

</process>

<success_criteria>
- Latest user intent classified.
- No file-changing tools used by the dispatcher.
- Implementation proceeds only when the latest user message contains exact phrase `implement` or `do it`.
- Structural issues discovered during work stop execution before patching.
- App/server lifecycle commands are not run by the agent.
- Removed or replaced behavior is not preserved as comments, aliases, shims, fallback branches, dead code, docs, or tests without user approval.
- Ambiguous requests are clarified before implementation.
</success_criteria>
