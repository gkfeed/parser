# 02: Introduce a ParserId domain type

**What to build:** Represent parser identifiers as a validated domain value across persistence, serialization, parser lookup, worker execution, and broker task routing.

**Blocked by:** None (can start immediately).

**Status:** ready

- [ ] Supported parser identifiers have one canonical definition outside the parser registry implementation.
- [ ] Values entering from the database or JSON are validated before registry or broker use.
- [ ] Worker APIs use a parser-specific name instead of the generic name `type`.
- [ ] Unsupported identifiers fail at a clear system boundary rather than during dispatch.
- [ ] Existing persisted values and broker task names remain compatible.
- [ ] `make lint` and `make test` pass.
