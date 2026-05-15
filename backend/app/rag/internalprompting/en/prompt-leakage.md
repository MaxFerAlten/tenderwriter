# Prompt Leakage Labels & Instructions (EN)

Regex fragments used to detect leakage of the internal prompt scaffolding in
LLM-generated text. Each group is a bullet list of regex alternatives spliced
verbatim into `(?:alt1|alt2|...)`. The `Instruction Lines` section contains
full regex patterns (one per line, anchored implicitly with `^...$`).

## Plain Labels

- draft ending
- task(?=\s*:|$)
- retrieved context
- user question
- response constraints
- important instructions
- user prompt
- retrieved snippet
- already written ending(?:\s*\([^)]*\))?

## Plain Answer Labels

- own answer
- your answer

## Heading Only Answer Labels

- answer(?:\s*\([^)]*\))?
- own answer
- your answer

## Loop Labels

- own answer
- your answer
- answer
- user question
- retrieved context
- response constraints
- draft ending
- task

## Inline Trigger Labels

- task
- user question
- retrieved context
- already written ending(?:\s*\([^)]*\))?
- response constraints
- important instructions

## User Query Verbs

- write
- give
- show
- explain
- describe
- analyze
- analyse
- summarize
- summarise
- list
- provide
- prepare
- generate
- find
- search
- indicate
- compare
- evaluate

## Instruction Lines

- write only the natural continuation of the answer, starting directly from the missing content\.?
- complete only what is needed to naturally close the last sentence or the last concept left unfinished\. start directly with the missing text\.?
- provide a helpful, accurate answer based on the available context\.?
- respond in the same language as the user(?:'s)? question\.?
- always respond in the same language as the user(?:'s)? question\.?
- use only the retrieved context\.?
- output only the answer text, no labels, no meta-commentary\.?
- if the context doesn't contain enough information, say so clearly\.?
- remember: respond in the same language as the question above!?
- start directly with the final answer, without copying headings or prompt sections\.?
- now continue directly from the point where the answer was interrupted\.?
- now complete only what is needed to naturally close the last sentence or the last concept left unfinished\.?
- start directly with the missing text\.?
- - you must respond in the same language as the user's question\.?
- - you are continuing an answer that was already started\.?
- - you must complete only the final sentence or concept that was left unfinished\.?
- - do not restart from the beginning\.?
- - do not repeat (?:sections or sentences that were already written|the text that was already written)\.?
- - do not comment on the word count\.?
- - do not write titles or phrases like "continuation of the answer"\.?
- - do not quote or copy internal prompt labels\.?
- - add only new, substantive content that is coherent with what was already written\.?
- - do not start a new paragraph, a new section, or a new topic\.?
- - write at most 60 words\.?
- - close with a complete and coherent sentence\.?
