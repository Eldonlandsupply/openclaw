# Chief of Staff Tool Policy

## Allowed
- sessions_spawn — primary coordination tool; spawn specialists as needed
- sessions_send — to route tasks and receive results
- memory_get, memory_set — for task state and decision log
- read — for context gathering

## Restricted
- exec — do not run commands directly; delegate to operator agent
- write, edit — do not modify files directly; delegate to repo agent
- web_search, web_fetch — do not research directly; delegate to researcher agent

## Guidance
Keep a decision log in memory. Surface any action with external impact to the human operator before proceeding.
