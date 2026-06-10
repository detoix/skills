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

<step name="display">
Show routing before dispatch:

Routing: {route}
Reason: {one-line reason}
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

<step name="internal_discovery_gate">
During any route that inspects, analyzes, or edits code, if the agent discovers that the requested change would patch around structurally wrong code or a bad pattern:

1. Stop before patching.
2. Diagnose the structural issue or bad pattern.
3. Present the decision to the user.
4. Wait for approval before continuing.
</step>

<step name="server_lifecycle_gate">
During any route, if the agent would start, stop, restart, or run the application/server/dev server:

1. Stop before running the command.
2. Do not start, stop, restart, or run the application/server/dev server.
3. State that the user runs the app/server.
4. Ask the user to run it or provide results if needed.
</step>

</process>

<success_criteria>
- Latest user intent classified.
- Routing decision displayed before dispatch.
- No file-changing tools used by the dispatcher.
- Implementation proceeds only when the latest user message contains exact phrase `implement` or `do it`.
- Structural issues discovered during work stop execution before patching.
- App/server lifecycle commands are not run by the agent.
- Ambiguous requests are clarified before implementation.
</success_criteria>
