.RECIPEPREFIX = >
.PHONY: sync test verify test-ts build

sync:
> python3 scripts/sync_corpus.py

test: sync
> cd python && PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'

verify:
> python3 scripts/sync_corpus.py --check
> python3 scripts/verify_readme_claims.py

test-ts:
> cd typescript && npm ci && npm test

build: sync
> cd python && python3 -m build
