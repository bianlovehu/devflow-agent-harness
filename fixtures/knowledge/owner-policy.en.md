<!-- Purpose: synthetic English policy for the multilingual retrieval demonstration. -->
# Taskboard ownership and optional labels

This document is a synthetic project policy for the DevFlow demonstration.

## Ownership boundary

Every user may read only tasks whose owner_id equals their actor_id. Listing all
tasks without checking ownership violates the isolation requirement AUTH-01.
This rule applies even if the caller already passed authentication.

## Optional labels

An omitted labels field, an explicit null, and an empty list all mean no labels.
The API must normalize these inputs to an empty list. Reject invalid non-list
values separately and preserve the documented null compatibility contract.
