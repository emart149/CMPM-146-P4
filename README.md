We chose to program the first 3 heuristics.
1. Pruning
   -We found that if the depth exceeds a certain amount, it starts to run on infinitely, and so we capped it at 1000
   -A problem we had early on was if planner was trying to produce a tool we already had. Similar to the flags we used in ManualHTN, we used getattr(state, product)[ID] >= 1 to check.
   -With test case D, we found it trying to produce item already in production so we then checked calling_stack.
2. Ordering Subtasks within a method.
   -We wrote set_order to sort through the consumes lists. This checks if one item(a) needs another item(b), that item(b)) subtask is placed in the correct order
3. Ordering Methods for a Task
   -We set up declare methods to sort by tier, time, and n_subtasks
   -For resources, we ran into an issue of using worse tools for a task wasting valuable time. So tool_select was made to use the best tool.
4. Ordering Methods for a Task
   -Unused