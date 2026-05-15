# QA Continuation Prompt (EN)

Template used to extend a long-form answer that was already started. The
`{query}`, `{context}`, and `{current_answer_tail}` placeholders are
interpolated at runtime.

<!-- prompt:start -->
IMPORTANT INSTRUCTIONS:
- You must respond in the SAME LANGUAGE as the user's question.
- You are continuing an answer that was already started.
- Do not restart from the beginning.
- Do not repeat sections or sentences that were already written.
- Do not comment on the word count.
- Do not write titles or phrases like "Continuation of the answer".
- Do not quote or copy internal prompt labels.
- If the draft contains broken OCR formulas or incomplete symbols, do not copy them blindly: rewrite the passage correctly or explain it in accurate prose.
- Add only new, substantive content that is coherent with what was already written.

USER QUESTION:
{query}

RETRIEVED CONTEXT:
{context}

ALREADY WRITTEN ENDING (reference only, do not copy):
{current_answer_tail}

Now continue directly from the point where the answer was interrupted.
Write only the natural continuation of the answer, starting directly from the missing content.
<!-- prompt:end -->
