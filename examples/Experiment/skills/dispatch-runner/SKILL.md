---
name: dispatch-runner
description: "Open and assign a concrete execution unit such as a subagent or agent team"
---

# /dispatch-runner — Open Execution Unit

Open and assign a managed execution unit for concrete experiment work.

## Goal

Once a request has been accepted and resources have been allocated, your next step is to delegate. A managed execution unit means a subagent or an agent team opened for concrete execution.

When you open that execution unit, load and follow `/execution-guide` as the default behavioral guide for the hands-on executor.

## Do

- choose whether one subagent is enough or an agent team is needed
- specify the concrete execution slice
- specify resource boundaries
- specify expected outputs and artifact locations
- keep the manager out of the hands-on work

## Do not do

- do not personally write scripts
- do not personally debug the experiment
- do not personally run the assigned task instead of delegating it

## Output

Return an execution handoff record:
- execution unit type
- assigned scope
- resource boundary
- expected outputs
- artifact destination
- tracking identifier