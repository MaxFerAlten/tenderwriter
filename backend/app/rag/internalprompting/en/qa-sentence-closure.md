# QA Sentence Closure Prompt (EN)

Template used to close a sentence or concept left unfinished at the end of a
generation pass. The `{query}`, `{context}`, and `{current_answer_tail}`
placeholders are interpolated at runtime.

<!-- prompt:start -->
IMPORTANT INSTRUCTIONS:
- You must respond in the SAME LANGUAGE as the user's question.
- You must complete only the final sentence or concept that was left unfinished.
- Do not start a new paragraph, a new section, or a new topic.
- Do not repeat the text that was already written.
- Write at most 60 words.
- Close with a complete and coherent sentence.
- Do not quote or copy internal prompt labels.

USER QUESTION:
{query}

RETRIEVED CONTEXT:
{context}

ALREADY WRITTEN ENDING (reference only, do not copy):
{current_answer_tail}

Now complete only what is needed to naturally close the last sentence or the last concept left unfinished.
Start directly with the missing text.
<!-- prompt:end -->
