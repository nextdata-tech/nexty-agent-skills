# Inventory Schema

Use these structures for the required run artifacts. JSON examples are illustrative; add fields when useful, but keep these core fields stable.

## `mesh-inventory.json`

```json
{
  "run": {
    "created_at": "YYYY-MM-DDTHH:MM:SSZ",
    "workspace": "/absolute/path",
    "mode": "blueprint|mesh-assisted",
    "mesh": {
      "name": null,
      "api_url": null,
      "config": null
    }
  },
  "domains": [
    {
      "name": "Commercial",
      "parent": null,
      "kind": "business",
      "owner_team": "Commercial Data",
      "steward": null,
      "evidence": ["evidence:domain-map-png"],
      "confidence": "medium",
      "notes": null
    }
  ],
  "cloud_footprint": [
    {
      "platform": "Snowflake",
      "clouds": ["AWS", "Azure"],
      "regions": ["AWS:us-east-1", "Azure:Frankfurt"],
      "account_count": 8,
      "env_split": ["dev", "test", "prod", "prod-commercial", "non-prod-commercial"],
      "owner_domain": "shared",
      "purpose": "Enterprise analytical backbone",
      "evidence": ["evidence:dap-assessment-section-1.2.2"],
      "confidence": "high",
      "notes": "Hybrid AWS+Azure."
    }
  ],
  "infra_profiles": [
    {
      "name": "commercial-aws",
      "domain": "Commercial",
      "primary_cloud": "AWS",
      "platforms": ["Snowflake", "S3"],
      "env_split": ["prod", "non-prod"],
      "evidence": ["evidence:dap-assessment-section-1.2.2"],
      "confidence": "medium",
      "status": "proposed"
    }
  ],
  "identities": [
    {
      "id": "identity:user@argenx.com",
      "kind": "user",
      "primary_id": "user@argenx.com",
      "display_name": null,
      "groups": ["dap-research-prod-readers"],
      "apps": ["Snowflake-Prod"],
      "domain_links": [{"domain": "Research", "role": "consumer", "confidence": "medium"}],
      "evidence": ["evidence:okta-export"],
      "confidence": "medium"
    }
  ],
  "roles": [
    {
      "id": "role:dap-research-readers",
      "members": ["identity:user@argenx.com"],
      "apps": ["Snowflake-Prod"],
      "proposed_domain": "Research",
      "proposed_function": "consumer",
      "evidence": ["evidence:okta-group-dap-research-prod-readers"],
      "confidence": "medium",
      "review_status": "pending"
    }
  ],
  "open_todos": [
    {
      "id": "#3",
      "phase": "cloud-footprint",
      "item": "Azure DevOps repo list",
      "blocker": "not handy",
      "added_at": "2026-05-06",
      "resolved_at": null
    }
  ],
  "state": {
    "phase": "cloud-footprint",
    "completed": ["prepare", "domain-map"],
    "in_progress": "cloud-footprint",
    "blocked_on": ["#3"]
  },
  "sources": [
    {
      "id": "snowflake:finance.raw",
      "kind": "snowflake|git|file|document|diagram|bi|api|stream|mesh|manual",
      "name": "finance raw schema",
      "location": "database/schema/path/url",
      "owner": null,
      "domain": null,
      "description": null,
      "evidence": ["evidence:1"],
      "confidence": "high|medium|low"
    }
  ],
  "assets": [
    {
      "id": "asset:orders",
      "source_id": "snowflake:finance.raw",
      "kind": "table|view|file|job|report|dashboard|document|model|api|topic",
      "name": "orders",
      "schema": [
        {
          "name": "order_id",
          "type": "string",
          "nullable": false,
          "description": null,
          "evidence": ["evidence:2"]
        }
      ],
      "freshness": {
        "partition_fields": [],
        "observed_schedule": null,
        "recommended_cron": null,
        "evidence": []
      },
      "dependencies": [],
      "consumers": [],
      "owner": null,
      "domain": null,
      "confidence": "high"
    }
  ],
  "evidence": [
    {
      "id": "evidence:1",
      "kind": "command|file|repo-path|user-confirmation|document-page|image|diagram|sample-profile",
      "location": "path/url/command",
      "excerpt": "short summary, not full copied content",
      "observed_at": "YYYY-MM-DDTHH:MM:SSZ"
    }
  ],
  "candidate_products": [
    {
      "name": "orders-source",
      "type": "source-aligned|domain|aggregate|serving|context-document",
      "domain": "finance",
      "owner": null,
      "steward": null,
      "purpose": "Expose source orders without changing shape.",
      "inputs": ["asset:orders"],
      "outputs": ["orders"],
      "dependencies": [],
      "freshness": {
        "recommended_cron": "0 2 * * *",
        "expectation": "daily freshness",
        "confidence": "medium"
      },
      "quality": {
        "expectations": ["schema match", "primary key present"],
        "promises": ["model schema promise"]
      },
      "evidence": ["evidence:1", "evidence:2"],
      "confidence": "medium",
      "risks": [],
      "missing_info": ["owner confirmation"]
    }
  ]
}
```

## `product-candidates.md`

For each candidate, include:

- Rank and first-wave/deferred status.
- Product name and type.
- Domain, owner, steward, and confidence.
- Inputs, outputs, dependencies, and consumers.
- Freshness and scheduler recommendation.
- Expected model promises and quality checks.
- Evidence summary.
- Risks and missing information.

## Draft Product Notes

Each generated draft product should include a concise note or comments tying generated choices back to inventory evidence. Use TODOs for unknowns instead of guessing:

- `TODO(owner)`: ownership not confirmed.
- `TODO(infra)`: compute/storage service not selected or unavailable.
- `TODO(schema)`: field type or description not confirmed.
- `TODO(freshness)`: schedule or partitioning not confirmed.
- `TODO(validation)`: validation command skipped or failed.
