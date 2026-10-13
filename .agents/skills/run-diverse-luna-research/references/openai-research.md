# OpenAI official-docs research

Read this lane when an OpenAI product/API change or current capability affects the user's decision. It adds domain-specific source choices to the existing evidence contract, without adding a setup requirement or changing the caller's model.

## Retrieve the actual contract

Use an exposed, working official Docs MCP to search, then fetch the matching page body. Its [service description](https://developers.openai.com/learn/docs-mcp) describes a read-only documentation service, not execution of the user's API. A configured connection and a successful search are separate observations. Search results locate evidence; they do not replace the supporting section.

If exposed tools are deferred or the inventory was shortened, use the runtime's tool discovery before treating the service as unavailable. Search payloads can duplicate full text in highlights: where orchestration permits, display bounded locators and omissions while retaining the raw response. Fetch a relevant section and check the actual heading; an unknown anchor may silently return the full page. Reduced output size is a measured serialization property, not proof of lower task cost or improved answer quality.

If the tools are absent or retrieval fails, use official web pages. When a Markdown endpoint returns an unsupported content type, open its canonical HTML page and inspect the relevant section; record the failed representation and the successful fallback. Do not repeat a denied representation without a changed condition. Use [the developer index](https://developers.openai.com/llms.txt) or [the ChatGPT index](https://learn.chatgpt.com/docs/llms.txt) only to find the relevant product area; index enumeration is not page-body coverage. Installation or authentication changes belong to the caller's authorized scope.

## Triangulate the decision-changing claims

For a recent feature or migration, align the dated release/changelog entry, the current feature reference, and the [deprecations list](https://developers.openai.com/api/docs/deprecations) when retirement can affect the decision. Fetch the matching migration guide when action is required. An older guide can remain indexed after its endpoint has retired. Resolve scope/date differences explicitly, or retain an uncertainty if the authoritative pages conflict.

Record publication/update date separately from retrieval time and effective/retirement date. For an undated current page, record “publication date unknown” rather than treating the retrieval date as its introduction. In a “latest” answer, state the searched cutoff and the relevant release window.

Bind each capability to its product, interface, model/version, authentication route, and rollout conditions where applicable:

- [Responses Multi-agent](https://developers.openai.com/api/docs/guides/responses-multi-agent), [Agents API multi-agent](https://developers.openai.com/api/docs/guides/agents-api/multi-agent), and Codex native subagents have separate contracts. A shared feature name does not transfer limits, tools, resource ownership, or beta eligibility across them.
- [Sign in with ChatGPT preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) and API-key access describe different authorization routes. Identity scopes, plan entitlements, and API resource permissions must be supported by their own reference.
- A CLI changelog establishes that CLI release's change; desktop availability needs its own evidence. A model catalog establishes documented support, while the current task's exposed tools and account access require direct observation.

The packet contract already defines dates, source families, and evidence gates. Apply it here: several OpenAI pages can cover distinct contracts but still count as one vendor family. Vendor launch claims and benchmarks support what OpenAI reports; independent effectiveness needs comparable original measurements. Advertised speed, a lower token price, or a shorter skill entrypoint does not establish task latency, success rate, or cost per successful task. State when account, runtime, or performance checks were not run, and retain the material limitation in the answer.

## Return evidence that can drive an improvement

When the user asks for changes, map each selected finding to the local target, the supported behavior change, a check that can observe it, and any unresolved external gate. The caller owns edits and tests; scouts remain evidence-only. Preserve the selected model, invocation policy, and existing mutation boundary. If the user has not named the target and the distinction changes which files should be edited, clarify that target while continuing independent research.

This lane was derived from the official-source research reviewed on 2026-10-04. URLs are refresh points, not frozen proof of future availability; the current source body controls a new answer.
