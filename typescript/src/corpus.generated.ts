// Generated from capsules/ by scripts/build_ts_corpus.py. Do not edit by hand.
export const CORPUS: unknown[] = [
  {
    "id": "github.merge_pr",
    "provider": "github",
    "operation": "merge_pr",
    "schema_version": "1",
    "summary": "Merge a pull request. Answer whether the merge actually happened, telling a real merge apart from a pull request whose branch was merely deleted.\n",
    "idempotency": {
      "strategy": "natural_key",
      "keys": [
        "owner",
        "repo",
        "pull_number"
      ],
      "notes": "A pull request is identified by owner, repo, and number. Merging one that is already merged returns 405, so the natural key is enough to recognize a repeat.\n"
    },
    "probe": {
      "kind": "http",
      "request": {
        "method": "GET",
        "path": "/repos/{owner}/{repo}/pulls/{pull_number}"
      },
      "interpret": [
        {
          "when": {
            "status_in": [
              200
            ],
            "json_path": "merged",
            "equals": true
          },
          "result": "landed"
        },
        {
          "when": {
            "status_in": [
              200
            ],
            "json_path": "merged",
            "equals": false
          },
          "result": "not_landed"
        },
        {
          "when": {
            "status_in": [
              404,
              500,
              502,
              503
            ]
          },
          "result": "unknown"
        }
      ]
    },
    "reversibility": {
      "class": "irreversible"
    },
    "compensation": {
      "kind": "none",
      "notes": "A merge commit is part of history and cannot be truly reversed. The only recourse is a revert, which is a new forward commit rather than an undo, so it is out of scope for a compensation and is left to the caller.\n"
    },
    "notes": "The merged field is authoritative. A pull request can look finished because its branch was deleted, yet merged is false, meaning the change never landed. Trusting branch state instead of the merged field is the trap this capsule removes.\n",
    "source": "https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request"
  },
  {
    "id": "postgres.insert",
    "provider": "postgres",
    "operation": "insert",
    "schema_version": "1",
    "summary": "Insert a row through a natural key. Answer whether the row committed after a crash, and reverse it with a keyed delete when nothing depends on it yet.\n",
    "idempotency": {
      "strategy": "natural_key",
      "keys": [
        "table",
        "key_column",
        "key_value"
      ],
      "notes": "The row carries a business key backed by a unique constraint. Re-running the insert then fails on the constraint rather than duplicating, which is what makes the natural key a safe idempotency handle.\n"
    },
    "probe": {
      "kind": "native",
      "handler": "postgres_row_exists"
    },
    "reversibility": {
      "class": "conditionally_reversible",
      "condition": "The row is addressable by its natural key and nothing else references it yet, so a keyed delete returns the table to its prior state. Once dependent rows exist the delete is no longer a clean reversal.\n"
    },
    "compensation": {
      "kind": "native",
      "handler": "postgres_delete_by_key",
      "notes": "Delete the row by its natural key inside its own transaction.\n"
    },
    "notes": "This capsule is native rather than http because the operation speaks the Postgres wire protocol through a driver, not REST. The probe and compensation are resolved to per-language handlers keyed by id, while the corpus stays the source of the meaning.\n",
    "source": "https://www.postgresql.org/docs/current/tutorial-transactions.html"
  },
  {
    "id": "s3.delete_object",
    "provider": "aws_s3",
    "operation": "delete_object",
    "schema_version": "1",
    "summary": "Delete an object from an S3 bucket. Answer whether the object is gone, and restore it only when bucket versioning kept the prior version.\n",
    "idempotency": {
      "strategy": "none",
      "notes": "Deleting an object is naturally idempotent. Repeating the delete against a missing key still returns success, so no idempotency key is needed.\n"
    },
    "probe": {
      "kind": "http",
      "request": {
        "method": "HEAD",
        "path": "/{bucket}/{key}"
      },
      "interpret": [
        {
          "when": {
            "status_in": [
              404
            ]
          },
          "result": "landed"
        },
        {
          "when": {
            "status_in": [
              200
            ]
          },
          "result": "not_landed"
        },
        {
          "when": {
            "status_in": [
              500,
              503
            ]
          },
          "result": "unknown"
        }
      ]
    },
    "reversibility": {
      "class": "conditionally_reversible",
      "condition": "Bucket versioning was enabled at delete time, so the delete wrote a delete marker and retained the previous version. Without versioning the object is gone for good.\n"
    },
    "compensation": {
      "kind": "http",
      "request": {
        "method": "DELETE",
        "path": "/{bucket}/{key}",
        "query": {
          "versionId": "{delete_marker_version_id}"
        }
      },
      "notes": "Restore by deleting the delete marker, which makes the most recent prior version current again. This needs the delete marker version id returned in the original delete response as x-amz-version-id, so capture it at delete time.\n"
    },
    "notes": "The probe reports whether the object currently resolves. On a versioned bucket a landed delete still leaves the data recoverable, which is why reversibility is conditional rather than outright.\n",
    "source": "https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeleteMarker.html"
  },
  {
    "id": "stripe.charge",
    "provider": "stripe",
    "operation": "charge",
    "schema_version": "1",
    "summary": "Create a payment on Stripe. After an ambiguous crash, answer whether the charge was created, and reverse it with a refund.\n",
    "idempotency": {
      "strategy": "client_key",
      "header": "Idempotency-Key",
      "notes": "Send a client-generated Idempotency-Key with the create request. A retry with the same key returns the original result instead of charging again. The key must be generated by the caller before the first attempt, never regenerated on retry, or the deduplication is bypassed.\n"
    },
    "probe": {
      "kind": "http",
      "request": {
        "method": "GET",
        "path": "/v1/payment_intents/search",
        "query": {
          "query": "metadata[\"order_id\"]:\"{order_id}\""
        }
      },
      "interpret": [
        {
          "when": {
            "status_in": [
              200
            ],
            "json_path": "data",
            "count_gte": 1
          },
          "result": "landed"
        },
        {
          "when": {
            "status_in": [
              200
            ]
          },
          "result": "not_landed"
        },
        {
          "when": {
            "status_in": [
              429,
              500,
              502,
              503
            ]
          },
          "result": "unknown"
        }
      ]
    },
    "reversibility": {
      "class": "reversible"
    },
    "compensation": {
      "kind": "http",
      "request": {
        "method": "POST",
        "path": "/v1/refunds",
        "query": {
          "payment_intent": "{payment_intent_id}"
        }
      },
      "notes": "Refund the payment intent found by the probe. A refund is a genuine reversal of the money movement, so this operation is fully reversible.\n"
    },
    "notes": "The probe uses the Search API keyed on the order_id you attach as metadata, which copies from the payment intent to its charge. Search is eventually consistent and can lag a created charge by a short window, so a not_landed result immediately after a crash should be re-checked before acting on it.\n",
    "source": "https://docs.stripe.com/api/payment_intents/search"
  }
];
