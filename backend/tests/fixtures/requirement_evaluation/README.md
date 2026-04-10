# Requirement Evaluation Fixtures

`gold_smoke.json` is a synthetic smoke fixture for the evaluator. It proves the runner and report contract work, but it is not a real quality benchmark.

Real benchmark files should use the same `requirement_evaluation.gold.v1` envelope and contain curated tenders with reviewed expected requirements, citations, and relations.

To create a reviewable draft from the current requirement graph, run:

```powershell
python -m app.export_requirement_gold_set --tender-id 12 --output reports\requirement-gold-draft.json
```

The exporter treats approved consolidated requirements as expected gold items and active consolidated requirements as predicted items, so reviewers can spot unapproved false positives before promoting the file to a real benchmark.

If a reviewed document should contain no requirements, keep it as a negative case:

```json
{
  "id": "negative-thesis-case",
  "negative_case": true,
  "expected_requirements": [],
  "predicted_requirements": []
}
```

Negative cases are useful for preventing regressions where academic or descriptive documents are incorrectly extracted as tender requirements.

Required shape:

```json
{
  "schema_version": "requirement_evaluation.gold.v1",
  "cases": [
    {
      "id": "real-tender-case-id",
      "expected_requirements": [{ "text": "..." }],
      "predicted_requirements": [{ "canonical_text": "...", "citations": [{ "quote": "..." }] }],
      "expected_relations": [{ "source_text": "...", "target_text": "...", "relation_type": "overrides" }],
      "predicted_relations": [{ "source_requirement_text": "...", "target_requirement_text": "...", "relation_type": "overrides" }]
    }
  ]
}
```
