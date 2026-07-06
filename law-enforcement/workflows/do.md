<purpose>
Analyze user intent and enforce workflow gates before file modification.
</purpose>

<process>

<step name="pre_flight_gate">
Before creating, editing, deleting, moving, formatting, or generating files:

If the latest user message does not contain exact phrase `do it` or `fix it` and does not use an explicit workspace-modifying command:
1. STOP.
2. Do not edit files.
3. Do not call file-writing tools.
4. Answer normally if the request is a question, review, investigation, or plan.

</step>

<step name="deviation_rules">
Apply during any route that inspects, analyzes, or edits code:

- Code or architecture quality concern: STOP before continuing, diagnose the concern, present decision to user, await approval.
- Server lifecycle command: STOP before running, state that user runs the app/server, await user-provided results if needed.
- Clean final state: When changing, removing, or replacing behavior, search the touched scope for obsolete names, comments, aliases, compatibility shims, fallback branches, dead code, stale docs/tests, negative instructions, and parallel rules. Remove them cleanly. If preserving residue may be necessary for compatibility, STOP, present the compatibility decision to user, and await approval.
- Unsure: STOP and ask.

Priority: STOP gates > implementation phrase.
</step>

</process>

<success_criteria>
- Pre-flight gate enforced.
- Deviation rules enforced.
</success_criteria>
