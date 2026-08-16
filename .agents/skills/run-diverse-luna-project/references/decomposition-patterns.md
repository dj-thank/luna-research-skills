# Decomposition patterns

Read this reference when a project is unfamiliar, cross-functional, or too entangled for an obvious file-based split. Select only patterns that reveal independent progress.

## Outcome tree

Start from acceptance criteria and split each into the smallest deliverable that can be verified alone. Use this for product work, releases, migrations, and multi-artifact requests. Keep interface decisions and final assembly at the root.

## Component ownership

Split by modules, services, packages, documents, or explicit file sets. Use this for implementation only when ownership is disjoint. Identify shared schemas, types, configuration, and entry points as root-owned integration surfaces.

## Perspective panel

Assign the same proposal or artifact to distinct stakeholders or disciplines. Useful perspectives include end user, operator, maintainer, security, privacy, performance, accessibility, cost, compliance, and business value. Give each agent one lens and require concrete findings tied to evidence.

## Lifecycle chain

Split discovery, design, implementation, data migration, documentation, rollout, observability, and rollback. Treat these as dependent nodes rather than concurrent work when later stages need earlier outputs.

## Red team and pre-mortem

Assign one agent to falsify the leading plan, find failure modes, or identify missing evidence. Use a fresh context and provide the artifact under test without the builder's rationale when validation integrity matters.

## Verification lattice

Separate checks that prove different boundaries: unit and integration tests, static analysis, build or packaging, artifact hashes, local runtime smoke, deployed service state, external network reachability, physical device behavior, and human experience. Passing one cell does not imply another.

## Selection check

Keep a proposed cell only when it has:

- a unique question, deliverable, ownership area, or verification boundary;
- inputs available when dispatched;
- a return packet the root can integrate;
- lower coordination cost than doing it at the root.

Merge cells that duplicate evidence. Serialize cells that edit shared surfaces. Drop cells whose likely output cannot change the plan or confidence.
