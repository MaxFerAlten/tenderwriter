# Requirement Analyzer Prompt (EN)

Template used to analyze a tender/RFP document and extract requirements.
Placeholder `{document_text}` is interpolated at runtime. Expected response is
a JSON array.

<!-- prompt:start -->
You are an expert at analyzing tender/RFP documents.
Extract and categorize all requirements from the following tender document text.

IMPORTANT: Respond in the SAME LANGUAGE as the tender document.

## Tender Document
{document_text}

For each requirement found, provide:
1. The requirement text (exact or closely paraphrased)
2. Category (technical, financial, legal, experience, staffing, timeline, etc.)
3. Priority (must-have, should-have, nice-to-have)

Format your response as a JSON array:
[
  {{
    "text": "requirement description",
    "category": "category",
    "priority": "must-have|should-have|nice-to-have"
  }}
]

## Extracted Requirements
<!-- prompt:end -->
